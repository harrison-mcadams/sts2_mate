"""
STS2 Companion - Gemini Flash AI Advisor.
Builds authoritative, ground-truth Slay the Spire 2 prompts,
enforces strict anti-STS1 hallucination directives, and calls Gemini Flash
for qualitative, strategic deck-building recommendations.
"""

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

logger = logging.getLogger("sts2_companion.ai_advisor")

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiSTS2Advisor:
    def __init__(
        self,
        cards_db: Dict[str, Dict[str, Any]],
        relics_db: Optional[Dict[str, Dict[str, Any]]] = None,
        player_stats: Optional[Dict[str, Any]] = None,
    ):
        self.cards_db = cards_db
        self.relics_db = relics_db or {}
        self.player_stats = player_stats or {}

    def update_player_stats(self, player_stats: Dict[str, Any]) -> None:
        self.player_stats = player_stats

    def build_prompt(
        self,
        offered_cards: List[Dict[str, Any]],
        active_run: Dict[str, Any],
    ) -> str:
        """
        Builds a comprehensive, grounded prompt detailing current run state,
        exact STS2 database definitions, and strict instructions to reject STS1 mechanics.
        """
        character = active_run.get("character", "Ironclad")
        floor = active_run.get("current_floor", 1)
        act = active_run.get("current_act", 1)
        ascension = active_run.get("ascension", 0)
        hp = active_run.get("current_hp", 0)
        max_hp = active_run.get("max_hp", 0)
        gold = active_run.get("gold", 0)

        # Summarize deck
        deck = active_run.get("deck", [])
        deck_summary = []
        for c in deck:
            name = c.get("display_name") or c.get("name", "Unknown")
            c_type = c.get("card_type", "")
            cost = c.get("cost", 1)
            ench = f" (Enchantment: {c['enchantment']})" if c.get("enchantment") else ""
            deck_summary.append(f"- {name} [{c_type}, Cost: {cost}]{ench}")

        # Summarize relics
        relics = active_run.get("relics", [])
        relic_summary = []
        for r in relics:
            rname = r.get("name", "Unknown")
            rdesc = r.get("description") or self.relics_db.get(r.get("id", ""), {}).get("description", "")
            relic_summary.append(f"- {rname}: {rdesc}")

        # Summarize potions
        potions = active_run.get("potions", [])
        potion_names = [p.get("name", "") for p in potions if p.get("name")]

        # Offered cards details
        offered_summary = []
        for oc in offered_cards:
            cid = oc.get("id", "")
            cname = oc.get("name", cid)
            ctype = oc.get("card_type") or oc.get("type", "Skill")
            rarity = oc.get("rarity", "Common")
            cost = oc.get("cost", 1)
            desc = oc.get("description") or oc.get("description_raw", "")
            
            # Personal win rate if available
            pstats = self.player_stats.get("cards", {}).get(cid, {})
            pstats_str = ""
            if pstats and pstats.get("offered", 0) > 0:
                pstats_str = f" | Personal Stats: Picked {pstats.get('picked', 0)}/{pstats.get('offered', 0)} times, Win Rate: {pstats.get('win_rate', 0)}%"

            offered_summary.append(
                f"### {cname} (ID: {cid})\n"
                f"- Type: {ctype} | Cost: {cost} | Rarity: {rarity}{pstats_str}\n"
                f"- Description: {desc}\n"
            )

        prompt = f"""You are an elite competitive coach and strategist for **Slay the Spire 2** (STS2).

CRITICAL DIRECTIVES & GUARDRAILS:
1. Slay the Spire 2 is a brand-new sequel. It has distinct cards, altered energy costs, changed numbers, enchantments, new enemies, new relics, and new bosses.
2. NEVER assume rules, card stats, or relic synergies from Slay the Spire 1 unless they are explicitly confirmed by the STS2 database information provided below.
3. If searching Google for community discussion, ONLY consider sources explicitly discussing Slay the Spire 2 or STS2 (2025/2026 early access/playtest). Completely ignore Slay the Spire 1 wikis and discussions.
4. Base all advice strictly on the provided deck list, active relics, floor position, and upcoming act challenges.

---
### CURRENT RUN STATE:
- Hero: {character}
- Current Position: Act {act}, Floor {floor} (Ascension {ascension})
- Health: {hp}/{max_hp} HP ({round(hp/max_hp*100, 1) if max_hp else 0}%)
- Gold: {gold}
- Potions: {', '.join(potion_names) if potion_names else 'None'}

### ACTIVE RELICS ({len(relics)}):
{chr(10).join(relic_summary) if relic_summary else '- None'}

### CURRENT DECK ({len(deck)} cards):
{chr(10).join(deck_summary)}

---
### OFFERED CARD REWARD CHOICES:
{chr(10).join(offered_summary)}

---
TASK:
Analyze the offered card reward in the context of this specific deck and Act {act} / Floor {floor} challenges.
Evaluate whether taking one of these cards is beneficial, or if skipping is optimal to preserve deck density.

You MUST respond ONLY with a valid JSON object following this exact schema:
{{
  "recommended_card": "Name of recommended card, or 'Skip'",
  "verdict": "Clear 1-sentence verdict headline (e.g. 'Pick Whirlwind: Fills your critical need for AOE before Act 1 Elites')",
  "should_skip": false,
  "tactical_reasoning": "2-3 sentences explaining the overarching strategic justification for this pick given the current deck composition and upcoming threats.",
  "deck_synergies": [
    "Specific interaction or synergy with a card or relic in current deck"
  ],
  "upcoming_threat_prep": "How this choice prepares the deck for the specific challenges of Act {act} (e.g. Gremlin Nob, Sentries, Slime Boss, Act 2 multi-target fights)",
  "card_evaluations": [
    {{
      "name": "Card Name",
      "verdict_tier": "Top Pick" | "Situational" | "Dilutes Deck" | "Skip",
      "analysis": "Short analysis of how this card specifically fits or clashes with current deck",
      "pros": ["Pro point 1", "Pro point 2"],
      "cons": ["Con point 1"]
    }}
  ]
}}
"""
        return prompt

    def call_gemini(
        self,
        prompt: str,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Sends the grounded prompt to the Gemini REST API.
        """
        effective_key = api_key or get_gemini_api_key()
        if not effective_key:
            return {
                "success": False,
                "error": "No Gemini API key configured. Please provide an API key in settings or set GEMINI_API_KEY environment variable.",
                "requires_key": True,
            }

        effective_model = model or get_gemini_model()
        url = f"{GEMINI_API_BASE}/{effective_model}:generateContent?key={effective_key}"

        cfg = load_config()
        use_search = cfg.get("enable_search_grounding", True)

        payload: Dict[str, Any] = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2,
                "maxOutputTokens": 2048,
            }
        }

        # Optional Google Search Grounding tool
        if use_search:
            payload["tools"] = [{"google_search": {}}]

        headers = {
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=12.0)
            if resp.status_code != 200:
                # If Google Search Grounding with responseMimeType failed, try fallback without search tool
                if use_search and resp.status_code in {400, 404}:
                    payload.pop("tools", None)
                    resp = requests.post(url, headers=headers, json=payload, timeout=10.0)

            if resp.status_code != 200:
                err_body = resp.text[:300]
                logger.error(f"Gemini API error ({resp.status_code}): {err_body}")
                return {
                    "success": False,
                    "error": f"Gemini API returned status {resp.status_code}: {err_body}",
                }

            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return {"success": False, "error": "No response candidate returned by Gemini."}

            parts = candidates[0].get("content", {}).get("parts", [])
            raw_text = "".join(p.get("text", "") for p in parts if "text" in p).strip()

            # Parse JSON from response text
            parsed = self._extract_json(raw_text)
            if not parsed:
                return {
                    "success": False,
                    "error": "Failed to parse structured JSON from Gemini output.",
                    "raw_text": raw_text,
                }

            return {
                "success": True,
                "model": effective_model,
                "data": parsed,
            }

        except requests.exceptions.Timeout:
            return {"success": False, "error": "Gemini API request timed out (12s limit)."}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"Network error calling Gemini: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error in call_gemini: {str(e)}"}

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        """Extracts and parses JSON object from model response text."""
        # 1. Direct JSON parse
        try:
            return json.loads(text)
        except Exception:
            pass

        # 2. Extract from markdown code block ```json ... ```
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

        # 3. Find outermost braces
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                pass

        return None

    def evaluate(
        self,
        offered_card_ids: List[str],
        active_run: Dict[str, Any],
        fallback_advisor: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        High-level evaluation method:
        Gathers card objects, calls Gemini Flash, and attaches heuristic fallback if needed.
        """
        # Resolve full card metadata from DB
        offered_cards = []
        for cid in offered_card_ids:
            cinfo = self.cards_db.get(cid)
            if cinfo:
                offered_cards.append(cinfo)
            else:
                offered_cards.append({
                    "id": cid,
                    "name": cid.replace("CARD.", "").replace("_", " ").title(),
                    "card_type": "Skill",
                    "rarity": "Common",
                    "cost": 1,
                    "description": "",
                })

        # Generate heuristic fallback for comparison or if API fails
        fallback_eval = None
        if fallback_advisor:
            try:
                fallback_eval = fallback_advisor.evaluate_reward(offered_card_ids, active_run)
            except Exception as e:
                logger.warning(f"Fallback advisor error: {e}")

        # Check API key before making prompt
        api_key = get_gemini_api_key()
        if not api_key:
            return {
                "success": False,
                "requires_api_key": True,
                "message": "Gemini API key is not configured. Add your key to activate Gemini 3.8 Flash analysis.",
                "fallback_evaluation": fallback_eval,
                "offered_cards": offered_cards,
            }

        prompt = self.build_prompt(offered_cards, active_run)
        ai_res = self.call_gemini(prompt, api_key=api_key)

        if not ai_res.get("success"):
            return {
                "success": False,
                "error": ai_res.get("error"),
                "fallback_evaluation": fallback_eval,
                "offered_cards": offered_cards,
            }

        return {
            "success": True,
            "provider": "gemini",
            "model": ai_res.get("model"),
            "recommendation": ai_res.get("data"),
            "fallback_evaluation": fallback_eval,
            "offered_cards": offered_cards,
        }
