"""
STS2 Companion - Unknown Room (?) & Event Advisor.
Parses all 60+ Slay the Spire 2 events from extracted game metadata,
evaluates choice trade-offs (HP sacrifice vs. relics vs. transforms vs. curses),
and provides risk-adjusted recommendations grounded in active run survivability.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("sts2_companion.event_advisor")


class STS2EventAdvisor:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.events_db: Dict[str, Dict[str, Any]] = {}
        self._load_events()

    def _load_events(self) -> None:
        """Parses event strings and choices from sts2_metadata.json."""
        meta_path = os.path.join(self.data_dir, "sts2_metadata.json")
        if not os.path.exists(meta_path):
            logger.warning(f"Metadata file not found at {meta_path}")
            return

        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw_events = data.get("events", {})

            parsed: Dict[str, Dict[str, Any]] = {}
            for k, v in raw_events.items():
                parts = k.split(".")
                eid = parts[0]
                if eid not in parsed:
                    parsed[eid] = {
                        "id": eid,
                        "key": eid,
                        "title": eid.replace("_", " ").title(),
                        "description": "",
                        "options": {},
                    }

                if len(parts) == 2 and parts[1] == "title":
                    parsed[eid]["title"] = v
                elif len(parts) >= 4 and parts[1] == "pages" and parts[3] == "options":
                    opt_key = parts[4]
                    prop = parts[5] if len(parts) > 5 else "title"
                    if opt_key not in parsed[eid]["options"]:
                        parsed[eid]["options"][opt_key] = {
                            "key": opt_key,
                            "title": opt_key.replace("_", " ").title(),
                            "description": "",
                        }
                    parsed[eid]["options"][opt_key][prop] = v
                elif len(parts) >= 3 and parts[1] == "pages" and parts[2] == "INITIAL" and len(parts) == 4 and parts[3] == "description":
                    parsed[eid]["description"] = v

            # Convert options dict to list and clean bbcode tags
            for eid, edata in parsed.items():
                opts_list = []
                for okey, oinfo in edata.get("options", {}).items():
                    clean_desc = self._clean_bbcode(oinfo.get("description", ""))
                    clean_title = self._clean_bbcode(oinfo.get("title", ""))
                    opts_list.append({
                        "key": okey,
                        "title": clean_title,
                        "description": clean_desc,
                    })
                edata["options_list"] = opts_list
                edata["clean_description"] = self._clean_bbcode(edata.get("description", ""))

            self.events_db = parsed
            logger.info(f"Loaded {len(self.events_db)} STS2 events into Event Advisor.")
        except Exception as e:
            logger.error(f"Error loading events from metadata: {e}")

    def _clean_bbcode(self, text: str) -> str:
        """Removes rich text formatting like [gold], [red], [sine], etc."""
        if not text:
            return ""
        # Remove BBCode-style tags
        cleaned = re.sub(r"\[/?[^\]]+\]", "", text)
        return cleaned.strip()

    def get_event_catalog(self, query: str = "") -> List[Dict[str, Any]]:
        """Returns sorted list of available events for UI autocompletes."""
        q = query.lower().strip()
        results = []
        for eid, edata in self.events_db.items():
            title = edata.get("title", "")
            if not edata.get("options_list"):
                # Skip events with no interactive choices
                continue
            if q and q not in title.lower() and q not in eid.lower():
                continue
            results.append({
                "id": eid,
                "title": title,
                "description": edata.get("clean_description", "")[:120] + "...",
                "options_count": len(edata.get("options_list", [])),
            })
        results.sort(key=lambda x: x["title"])
        return results

    def resolve_event(self, event_identifier: str) -> Optional[Dict[str, Any]]:
        """Resolves event name or ID to database entry."""
        clean = event_identifier.strip().upper().replace("EVENT.", "").replace(" ", "_")
        if clean in self.events_db:
            return self.events_db[clean]
        for eid, edata in self.events_db.items():
            if edata.get("title", "").lower() == event_identifier.strip().lower():
                return edata
            if eid.lower() == clean.lower():
                return edata
        return None

    def evaluate_event(
        self,
        event_identifier: str,
        active_run: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Evaluates an unknown room event's choices against the player's active run.
        """
        edata = self.resolve_event(event_identifier)
        if not edata:
            return {
                "success": False,
                "error": f"Event '{event_identifier}' not found in STS2 database.",
                "event": None,
                "options": [],
                "recommended": None,
                "verdict": "Unknown event.",
            }

        current_hp = active_run.get("current_hp", 60)
        max_hp = active_run.get("max_hp", 80)
        hp_ratio = current_hp / max(max_hp, 1)
        deck = active_run.get("deck", [])
        gold = active_run.get("gold", 100)
        act = active_run.get("current_act", 1)
        relics = [r.get("name", "").lower() for r in active_run.get("relics", [])]

        # Calculate starter strike/defend count
        starter_strikes = sum(1 for c in deck if "strike" in c.get("name", "").lower() and "twin" not in c.get("name", "").lower() and "pommel" not in c.get("name", "").lower())
        starter_defends = sum(1 for c in deck if "defend" in c.get("name", "").lower())
        starter_count = starter_strikes + starter_defends

        evaluated_options = []

        for opt in edata.get("options_list", []):
            title = opt.get("title", "")
            desc = opt.get("description", "").lower()
            key = opt.get("key", "")

            score = 6.0
            risk_level = "SAFE"
            priority = "VIABLE"
            reasoning = "Standard event choice."

            # 1. HP Loss / Damage check
            if any(w in desc for w in ["take", "lose", "damage"]) and "hp" in desc:
                if hp_ratio < 0.35 or current_hp <= 22:
                    score = 2.0
                    risk_level = "LETHAL RISK"
                    priority = "DANGEROUS / SKIP"
                    reasoning = f"Severe danger: Your HP ({current_hp}/{max_hp}) is critically low. Sacrificing health risks death in upcoming rooms."
                elif hp_ratio < 0.55:
                    score = 4.8
                    risk_level = "HIGH RISK"
                    priority = "RISKY"
                    reasoning = "Substantial damage risk without a comfortable health buffer."
                else:
                    # High HP can afford aggressive trades for relics/perks
                    if any(w in desc for w in ["relic", "max hp", "card", "colorless"]):
                        score = 8.8
                        risk_level = "SAFE"
                        priority = "STRONG VALUE"
                        reasoning = f"Your health ({current_hp}/{max_hp}) provides a safe buffer to purchase permanent power."
                    else:
                        score = 6.2
                        risk_level = "MODERATE"
                        priority = "VIABLE"
                        reasoning = "Acceptable health trade if the outcome fits your plan."

            # 2. Card Removal / Transform / Thinning
            elif any(w in desc for w in ["remove", "transform", "combine"]):
                strike_focus = "strike" in desc or "strike" in title.lower()
                defend_focus = "defend" in desc or "defend" in title.lower()

                if starter_count >= 4:
                    score = 9.0
                    if strike_focus and starter_strikes >= starter_defends:
                        score += 0.4
                    elif defend_focus and starter_defends > starter_strikes:
                        score += 0.4
                    risk_level = "SAFE"
                    priority = "RECOMMENDED"
                    reasoning = f"High deck thinning value: cutting starter cards ({starter_strikes} Strikes, {starter_defends} Defends) immediately increases draw density for key engine cards."
                else:
                    score = 7.5
                    risk_level = "SAFE"
                    priority = "STRONG VALUE"
                    reasoning = "Deck refinement opportunity to cycle synergy pieces faster."

            # 3. Heal / Abstain / Rest
            elif any(w in desc for w in ["heal", "abstain", "rest", "leave"]):
                if hp_ratio <= 0.45:
                    score = 9.4
                    risk_level = "SAFE"
                    priority = "RECOMMENDED"
                    reasoning = f"Urgent recovery: sitting at {current_hp}/{max_hp} HP makes immediate healing top priority."
                elif hp_ratio >= 0.85:
                    score = 3.5
                    risk_level = "SAFE"
                    priority = "SKIP / LOW VALUE"
                    reasoning = f"You are already near full HP ({current_hp}/{max_hp}); healing provides minimal marginal benefit."
                else:
                    score = 6.0
                    risk_level = "SAFE"
                    priority = "VIABLE"
                    reasoning = "Safe sustain choice."

            # 4. Curse Gain
            elif "curse" in desc:
                has_omamori = "omamori" in relics
                if has_omamori:
                    score = 9.0
                    risk_level = "SAFE"
                    priority = "RECOMMENDED"
                    reasoning = "Omamori completely blocks the curse! Take the powerful reward risk-free."
                elif gold >= 150:
                    score = 7.0
                    risk_level = "MODERATE"
                    priority = "VIABLE"
                    reasoning = "You have enough gold to purge this curse at an upcoming merchant."
                else:
                    score = 3.8
                    risk_level = "HIGH RISK"
                    priority = "RISKY"
                    reasoning = "Adds unplayable clutter to your deck without an immediate purge plan."

            # 5. Card Upgrade
            elif any(w in desc for w in ["upgrade", "maintain control"]):
                score = 8.6
                risk_level = "SAFE"
                priority = "STRONG VALUE"
                reasoning = "Permanent card power increase without spending camp smithing actions."

            # 6. Combat / Fight
            elif any(w in desc for w in ["fight", "battle"]):
                if hp_ratio >= 0.6:
                    score = 8.2
                    risk_level = "MODERATE"
                    priority = "STRONG VALUE"
                    reasoning = "Engaging combat yields valuable gold, potion, and card rewards with manageable risk."
                else:
                    score = 4.0
                    risk_level = "HIGH RISK"
                    priority = "DANGEROUS / SKIP"
                    reasoning = "Unnecessary combat when HP is vulnerable."

            evaluated_options.append({
                "key": key,
                "title": title,
                "description": opt.get("description", ""),
                "score": score,
                "risk_level": risk_level,
                "priority": priority,
                "reasoning": reasoning,
            })

        # Sort options by score descending
        evaluated_options.sort(key=lambda x: x["score"], reverse=True)
        recommended = evaluated_options[0] if evaluated_options else None

        verdict = f"Event Verdict: Pick '{recommended['title']}' — {recommended['reasoning']}" if recommended else "Review options carefully."

        return {
            "success": True,
            "event": {
                "id": edata.get("id"),
                "title": edata.get("title"),
                "description": edata.get("clean_description"),
            },
            "options": evaluated_options,
            "recommended": recommended,
            "verdict": verdict,
            "gemini_advice": verdict,
        }
