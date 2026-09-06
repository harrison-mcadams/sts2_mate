"""
STS2 Companion - Gemini-Powered Deck Engine & Strategy Coach.
Provides holistic deck evaluation: archetype identification, combat playbook,
turn sequencing, what to look for, what to avoid, card removal priorities,
and interactive deck Q&A.
"""

import hashlib
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
import requests

from sts2_companion.core.config import (
    get_gemini_api_key,
    get_gemini_model,
    load_config,
)
from sts2_companion.advisor.archetypes import infer_card_roles, ROLE_LABELS

logger = logging.getLogger("sts2_companion.deck_engine")

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiDeckEngine:
    def __init__(
        self,
        cards_db: Dict[str, Dict[str, Any]],
        relics_db: Optional[Dict[str, Dict[str, Any]]] = None,
        player_stats: Optional[Dict[str, Any]] = None,
    ):
        self.cards_db = cards_db
        self.relics_db = relics_db or {}
        self.player_stats = player_stats or {}
        self._analysis_cache: Dict[str, Dict[str, Any]] = {}

    def update_player_stats(self, player_stats: Dict[str, Any]) -> None:
        self.player_stats = player_stats

    def _generate_cache_key(self, active_run: Dict[str, Any]) -> str:
        deck = active_run.get("deck", [])
        relics = active_run.get("relics", [])
        floor = active_run.get("current_floor", 1)
        character = active_run.get("character", "Ironclad")
        deck_ids = ",".join(sorted(c.get("id", "") for c in deck))
        relic_ids = ",".join(sorted(r.get("id", "") for r in relics))
        raw = f"{character}:{floor}:{deck_ids}:{relic_ids}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def build_deck_prompt(self, active_run: Dict[str, Any]) -> str:
        """
        Builds a comprehensive grounded prompt detailing the player's full deck,
        relics, potions, act, floor, upcoming boss, and strict STS2 rules.
        """
        character = active_run.get("character", "Ironclad")
        floor = active_run.get("current_floor", 1)
        act = active_run.get("current_act", 1)
        hp = active_run.get("current_hp", 80)
        max_hp = active_run.get("max_hp", 80)
        gold = active_run.get("gold", 0)

        deck = active_run.get("deck", [])
        relics = active_run.get("relics", [])
        potions = active_run.get("potions", [])

        # Build deck item summary
        deck_items = []
        for c in deck:
            cid = c.get("id", "")
            cinfo = self.cards_db.get(cid, c)
            cname = cinfo.get("name", cid.replace("CARD.", "").replace("_", " ").title())
            ctype = cinfo.get("card_type", "Skill")
            cost = cinfo.get("cost", 1)
            desc = cinfo.get("description") or cinfo.get("description_raw", "")
            deck_items.append(f"- {cname} [{ctype}, Cost: {cost}]: {desc}")

        # Build relic summary
        relic_items = []
        for r in relics:
            rid = r.get("id", "")
            rinfo = self.relics_db.get(rid, r)
            rname = rinfo.get("name", rid.replace("RELIC.", "").replace("_", " ").title())
            rdesc = rinfo.get("description") or rinfo.get("description_raw", "")
            relic_items.append(f"- {rname}: {rdesc}")

        # Potion summary
        potion_names = [p.get("name", "") for p in potions if p.get("name")]
        potion_str = ", ".join(potion_names) if potion_names else "None"

        # Deck composition breakdown
        attacks = sum(1 for c in deck if c.get("card_type") == "Attack")
        skills = sum(1 for c in deck if c.get("card_type") == "Skill")
        powers = sum(1 for c in deck if c.get("card_type") == "Power")
        curses = sum(1 for c in deck if c.get("card_type") == "Curse")

        prompt = f"""You are the authoritative Slay the Spire 2 (STS2) Grandmaster Deck Coach.
Your goal is to deeply analyze the player's current run and provide an actionable, high-level tactical blueprint.

CRITICAL INSTRUCTIONS & ANTI-HALLUCINATION RULES:
1. This is Slay the Spire 2 (STS2), NOT STS1! Only refer to real cards, mechanics, and relics that exist in STS2. Do not invent non-existent mechanics.
2. Ground all advice directly in the player's exact cards, relics, and immediate floor threats.
3. Be specific and concise. Do not speak in vague platitudes. Name exact cards and combos.
4. Output MUST be valid, strict JSON matching the specified schema with NO extra markdown preamble or closing text.

=== CURRENT RUN CONTEXT ===
- Character: {character}
- Location: Act {act}, Floor {floor}
- Health: {hp}/{max_hp} ({round(hp/max_hp*100) if max_hp > 0 else 0}% HP) | Gold: {gold}
- Deck Size: {len(deck)} cards ({attacks} Attacks, {skills} Skills, {powers} Powers, {curses} Curses)
- Potions Held: {potion_str}

=== EQUIPPED RELICS ({len(relics)}) ===
{chr(10).join(relic_items) if relic_items else "None"}

=== COMPLETE ACTIVE DECK ({len(deck)} CARDS) ===
{chr(10).join(deck_items)}

=== OUTPUT JSON SCHEMA ===
Return a single JSON object with these exact keys:
{{
  "build_name": "Short descriptive title of the archetype (e.g. 'Strength-Scaling Heavy Burst', 'Exhaust Control Engine', 'Ironclad Starter Transition')",
  "build_stage": "One of: 'Starter Transition' | 'Core Engine Forming' | 'Synergy Online' | 'Fully Scaled'",
  "core_win_condition": "1-2 sentences explaining exactly how this deck defeats bosses and high-HP elites.",
  "playbook": {{
    "turn_1_2_priority": "Specific setup rules for opening turns (e.g. which powers or debuffs to play first, when to prioritize block).",
    "key_sequencing": [
      "Exact rule 1 (e.g. Always play Bash before multi-hit attacks to maximize Vulnerable)",
      "Exact rule 2 (e.g. Hold True Grit to exhaust starter Strikes and curses before skills)",
      "Exact rule 3 (e.g. When above 50% HP, take 4-6 damage to get Inflame into play early)"
    ],
    "mitigation_rule": "Advice on balancing defense vs racing damage in hallway fights vs boss fights."
  }},
  "what_to_look_for": {{
    "priority_cards": [
      {{"card_name": "Name of real STS2 card", "why": "Why this specific card solves a deck gap or amplifies an active combo"}},
      {{"card_name": "Name of real STS2 card", "why": "Explanation"}},
      {{"card_name": "Name of real STS2 card", "why": "Explanation"}}
    ],
    "priority_relics": [
      {{"relic_name": "Name of real STS2 relic", "why": "Why to buy or hunt this relic"}},
      {{"relic_name": "Name of real STS2 relic", "why": "Explanation"}}
    ],
    "priority_potions": [
      {{"potion_name": "Name of potion", "why": "Specific encounter or problem it solves"}}
    ]
  }},
  "what_to_avoid": [
    {{"target": "Card or relic type to decline", "danger_reason": "Why this is a trap or anti-synergy for this specific deck"}},
    {{"target": "Card or relic type to decline", "danger_reason": "Explanation"}}
  ],
  "card_removal_priority": [
    {{"card_name": "Exact card in deck", "reason": "Why this is the lowest value card to remove first at next merchant"}}
  ],
  "boss_matchup": {{
    "threat_assessment": "How this deck currently matches up against upcoming Act threats and what is missing to survive them."
  }}
}}
"""
        return prompt

    def call_gemini(self, prompt: str, api_key: Optional[str] = None, model: Optional[str] = None) -> Dict[str, Any]:
        """Calls the Gemini REST API with model fallback and strict error handling."""
        effective_key = api_key or get_gemini_api_key()
        if not effective_key:
            return {
                "success": False,
                "error": "No Gemini API key configured. Please enter your key in settings or set the GEMINI_API_KEY environment variable.",
            }

        effective_model = model or get_gemini_model()
        url = f"{GEMINI_API_BASE}/{effective_model}:generateContent?key={effective_key}"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "topP": 0.95,
                "responseMimeType": "application/json",
            },
        }

        headers = {"Content-Type": "application/json"}

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=16)

            if resp.status_code != 200:
                # Try fallback models
                fallback_chain = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.7-flash"]
                for fb_model in fallback_chain:
                    if fb_model != effective_model:
                        fb_url = f"{GEMINI_API_BASE}/{fb_model}:generateContent?key={effective_key}"
                        try:
                            fb_resp = requests.post(fb_url, json=payload, headers=headers, timeout=12)
                            if fb_resp.status_code == 200:
                                resp = fb_resp
                                effective_model = fb_model
                                break
                        except Exception:
                            continue

            if resp.status_code != 200:
                err_text = resp.text
                if resp.status_code == 429:
                    return {
                        "success": False,
                        "error": "Google Gemini quota limit reached for this API key. Wait a moment before retrying.",
                    }
                return {
                    "success": False,
                    "error": f"Gemini API returned error {resp.status_code}: {err_text[:200]}",
                }

            result_json = resp.json()
            candidates = result_json.get("candidates", [])
            if not candidates:
                return {"success": False, "error": "No candidate returned by Gemini."}

            text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if not text:
                return {"success": False, "error": "Empty text response from Gemini."}

            # Parse JSON
            cleaned_text = re.sub(r"^```json\s*", "", text.strip(), flags=re.MULTILINE)
            cleaned_text = re.sub(r"```$", "", cleaned_text.strip(), flags=re.MULTILINE).strip()

            data = json.loads(cleaned_text)
            return {
                "success": True,
                "model": effective_model,
                "data": data,
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Gemini deck engine: {e}")
            return {"success": False, "error": f"Failed to parse structured JSON: {str(e)}"}
        except requests.exceptions.Timeout:
            return {"success": False, "error": "Gemini API request timed out (16s limit)."}
        except Exception as e:
            logger.error(f"Error in Gemini call: {e}")
            return {"success": False, "error": str(e)}

    def analyze_deck(self, active_run: Dict[str, Any], force_refresh: bool = False) -> Dict[str, Any]:
        """
        Analyzes the player's active deck.
        Uses cache if run state is unchanged, otherwise queries Gemini.
        Falls back to local heuristic deck analysis if Gemini key is missing or offline.
        """
        cache_key = self._generate_cache_key(active_run)
        if not force_refresh and cache_key in self._analysis_cache:
            return self._analysis_cache[cache_key]

        api_key = get_gemini_api_key()

        if api_key:
            prompt = self.build_deck_prompt(active_run)
            res = self.call_gemini(prompt, api_key=api_key)
            if res.get("success"):
                out = {
                    "success": True,
                    "provider": "gemini",
                    "model": res.get("model", "gemini-flash"),
                    "data": res.get("data", {}),
                    "is_cached": False,
                }
                self._analysis_cache[cache_key] = out
                return out
            else:
                logger.warning(f"Gemini call failed ({res.get('error')}), using heuristic fallback.")

        # Fallback to local heuristic deck engine
        heuristic_data = self._generate_heuristic_deck_analysis(active_run)
        out = {
            "success": True,
            "provider": "heuristic",
            "model": "Local Heuristic Engine",
            "data": heuristic_data,
            "has_key": bool(api_key),
            "is_cached": False,
        }
        self._analysis_cache[cache_key] = out
        return out

    def _generate_heuristic_deck_analysis(self, active_run: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deterministic, offline rule-based deck analysis.
        Audits roles, detects archetype tendencies, and surfaces removal priorities.
        """
        deck = active_run.get("deck", [])
        relics = active_run.get("relics", [])
        act = active_run.get("current_act", 1)
        floor = active_run.get("current_floor", 1)
        character = active_run.get("character", "Ironclad")

        deck_size = len(deck)
        attacks = [c for c in deck if c.get("card_type") == "Attack"]
        skills = [c for c in deck if c.get("card_type") == "Skill"]
        powers = [c for c in deck if c.get("card_type") == "Power"]

        # Check roles
        role_counts: Dict[str, int] = {}
        for c in deck:
            cinfo = self.cards_db.get(c.get("id"), c)
            for r in infer_card_roles(cinfo):
                role_counts[r] = role_counts.get(r, 0) + 1

        strength_cnt = role_counts.get("strength", 0)
        exhaust_cnt = role_counts.get("exhaust", 0)
        aoe_cnt = role_counts.get("aoe_damage", 0)
        block_cnt = role_counts.get("block", 0)

        # Infer build name
        if strength_cnt >= 1:
            build_name = f"{character} Strength-Scaling"
            build_stage = "Synergy Online" if strength_cnt >= 2 else "Core Engine Forming"
            win_con = "Scale Strength with powers/skills and multiply damage across high-damage attacks."
        elif exhaust_cnt >= 2:
            build_name = f"{character} Exhaust Engine"
            build_stage = "Core Engine Forming"
            win_con = "Trigger on-exhaust relics and powers to generate infinite block and card velocity."
        elif deck_size <= 13 and floor <= 5:
            build_name = f"{character} Early Floor Starter"
            build_stage = "Starter Transition"
            win_con = "Frontload attack burst to kill Act 1 Elites before they scale."
        else:
            build_name = f"{character} Balanced Midrange"
            build_stage = "Core Engine Forming"
            win_con = "Balance sturdy block mitigation with high-efficiency damage."

        # Key sequencing
        sequencing = [
            "Play Vulnerable inflicters (Bash, Shockwave) before other attacks for +50% damage.",
            "Prioritize keeping Block density above 40% so defensive turns do not bleed HP.",
        ]
        if strength_cnt > 0:
            sequencing.append("Get Strength scaling cards into play early against multi-turn elites and bosses.")

        # Wishlist
        cards_wanted = []
        if aoe_cnt == 0:
            cards_wanted.append({"card_name": "Whirlwind / Breakthrough", "why": "Immediate AOE solution for Act 2 multi-enemy combats."})
        if strength_cnt > 0:
            cards_wanted.append({"card_name": "Twin Strike / Pummel", "why": "Multi-hit attacks scale multiple times per hit with your Strength."})
        cards_wanted.append({"card_name": "Shrug It Off / Blood Wall", "why": "Solid block additions to stabilize high damage turns."})

        # Avoid list
        avoid_list = [
            {"target": "Excessive basic attacks", "danger_reason": f"Deck already has {len(attacks)} attacks; taking more dilutes defensive consistency."},
            {"target": "Slow, un-synergistic 2-cost powers", "danger_reason": "Dead draws in early hallway fights before energy relics."}
        ]

        # Removal priority (basic strikes/defends)
        purge_list = []
        for c in deck:
            cname = c.get("name", "")
            if "Strike" in cname and cname != "Twin Strike" and cname != "Pommel Strike":
                purge_list.append({"card_name": cname, "reason": "Basic starter strike with lowest damage efficiency per energy."})
                if len(purge_list) >= 2:
                    break
        if not purge_list:
            purge_list.append({"card_name": "Strike", "reason": "Standard starter strike removal."})

        return {
            "build_name": build_name,
            "build_stage": build_stage,
            "core_win_condition": win_con,
            "playbook": {
                "turn_1_2_priority": "Setup Vulnerable or key powers, ensuring at least 12+ block on dangerous incoming turns.",
                "key_sequencing": sequencing,
                "mitigation_rule": "Take 3-5 chip damage if it guarantees setting up your scaling power on Turn 1.",
            },
            "what_to_look_for": {
                "priority_cards": cards_wanted[:3],
                "priority_relics": [
                    {"relic_name": "Akabeko / Vajra", "why": "Passive damage boost accelerates opening turn burst."},
                    {"relic_name": "Horn Cleat / Anchor", "why": "Covers early turn defense while powers are played."}
                ],
                "priority_potions": [
                    {"potion_name": "Strength / Fire Potion", "why": "Burst damage safety net against upcoming Elites."}
                ]
            },
            "what_to_avoid": avoid_list,
            "card_removal_priority": purge_list,
            "boss_matchup": {
                "threat_assessment": f"Currently on Act {act}, Floor {floor}. Ensure you have at least 1 reliable AOE card and 1 scaling damage engine before the Act Boss."
            }
        }

    def chat_about_deck(
        self,
        user_message: str,
        active_run: Dict[str, Any],
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Interactive Q&A with Gemini regarding current deck decisions, pathing, and upgrades.
        """
        api_key = get_gemini_api_key()
        if not api_key:
            return {
                "success": False,
                "error": "Gemini API key not configured. Please add your key in settings to chat with the Deck Coach.",
            }

        effective_model = get_gemini_model()
        url = f"{GEMINI_API_BASE}/{effective_model}:generateContent?key={api_key}"

        deck_prompt_context = self.build_deck_prompt(active_run)

        history_parts = []
        if conversation_history:
            for msg in conversation_history[-6:]:
                role = "user" if msg.get("role") == "user" else "model"
                history_parts.append({"role": role, "parts": [{"text": msg.get("content", "")}]})

        system_instruction = (
            "You are the Slay the Spire 2 Grandmaster Deck Coach. "
            "Answer the user's specific strategic question directly, concisely, and with authoritative tactical knowledge of STS2. "
            "Refer to their exact cards, relics, and deck size in your answer."
        )

        current_msg = f"{deck_prompt_context}\n\n=== USER QUESTION ===\n{user_message}"
        history_parts.append({"role": "user", "parts": [{"text": current_msg}]})

        payload = {
            "contents": history_parts,
            "generationConfig": {
                "temperature": 0.4,
                "topP": 0.95,
            },
        }

        try:
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=16)
            if resp.status_code != 200:
                return {"success": False, "error": f"Gemini API returned error {resp.status_code}: {resp.text[:150]}"}

            res_json = resp.json()
            candidates = res_json.get("candidates", [])
            if not candidates:
                return {"success": False, "error": "No response returned by Gemini."}

            reply_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return {
                "success": True,
                "reply": reply_text,
                "model": effective_model,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


# Singleton instance
_deck_engine_instance: Optional[GeminiDeckEngine] = None

def get_deck_engine(cards_db: Optional[Dict[str, Any]] = None, relics_db: Optional[Dict[str, Any]] = None) -> GeminiDeckEngine:
    global _deck_engine_instance
    if _deck_engine_instance is None:
        if cards_db is None:
            cards_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "sts2_cards.json")
            if os.path.exists(cards_path):
                with open(cards_path, "r", encoding="utf-8") as f:
                    cards_db = json.load(f)
            else:
                cards_db = {}
        if relics_db is None:
            relics_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "sts2_relics.json")
            if os.path.exists(relics_path):
                with open(relics_path, "r", encoding="utf-8") as f:
                    relics_db = json.load(f)
            else:
                relics_db = {}
        _deck_engine_instance = GeminiDeckEngine(cards_db, relics_db)
    return _deck_engine_instance
