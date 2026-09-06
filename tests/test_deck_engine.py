"""
Unit tests for Gemini Deck Engine and Strategy Coach.
"""

import json
import unittest
from unittest.mock import patch, MagicMock

from sts2_companion.advisor.deck_engine import GeminiDeckEngine
from sts2_companion.web.app import create_app


class TestDeckEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("data/sts2_cards.json", "r", encoding="utf-8") as f:
            cls.cards_db = json.load(f)
        with open("data/sts2_relics.json", "r", encoding="utf-8") as f:
            cls.relics_db = json.load(f)

        cls.engine = GeminiDeckEngine(cls.cards_db, cls.relics_db)
        cls.app = create_app()
        cls.client = cls.app.test_client()

        cls.mock_run = {
            "character": "Ironclad",
            "current_floor": 4,
            "current_act": 1,
            "current_hp": 68,
            "max_hp": 80,
            "gold": 95,
            "deck": [
                {"id": "CARD.STRIKE_IRONCLAD", "name": "Strike", "card_type": "Attack", "cost": 1},
                {"id": "CARD.STRIKE_IRONCLAD", "name": "Strike", "card_type": "Attack", "cost": 1},
                {"id": "CARD.DEFEND_IRONCLAD", "name": "Defend", "card_type": "Skill", "cost": 1},
                {"id": "CARD.BASH", "name": "Bash", "card_type": "Attack", "cost": 2},
                {"id": "CARD.INFLAME", "name": "Inflame", "card_type": "Power", "cost": 1},
                {"id": "CARD.DISMANTLE", "name": "Dismantle", "card_type": "Attack", "cost": 1},
            ],
            "relics": [
                {"id": "RELIC.BURNING_BLOOD", "name": "Burning Blood"}
            ],
            "potions": [
                {"id": "POTION.FIRE", "name": "Fire Potion"}
            ],
        }

    def test_build_deck_prompt(self):
        """Verify prompt builder formats deck, relics, potions, and anti-hallucination directives."""
        prompt = self.engine.build_deck_prompt(self.mock_run)
        self.assertIn("Ironclad", prompt)
        self.assertIn("Inflame", prompt)
        self.assertIn("Dismantle", prompt)
        self.assertIn("Burning Blood", prompt)
        self.assertIn("Fire Potion", prompt)
        self.assertIn("ANTI-HALLUCINATION RULES", prompt)
        self.assertIn("Slay the Spire 2", prompt)

    def test_heuristic_fallback_analysis(self):
        """Verify offline heuristic analysis produces complete structured blueprint."""
        res = self.engine.analyze_deck(self.mock_run)
        self.assertTrue(res["success"])
        data = res["data"]

        # Check required schema keys
        self.assertIn("build_name", data)
        self.assertIn("build_stage", data)
        self.assertIn("core_win_condition", data)
        self.assertIn("playbook", data)
        self.assertIn("turn_1_2_priority", data["playbook"])
        self.assertIn("key_sequencing", data["playbook"])

        self.assertIn("what_to_look_for", data)
        self.assertGreater(len(data["what_to_look_for"]["priority_cards"]), 0)

        self.assertIn("what_to_avoid", data)
        self.assertGreater(len(data["what_to_avoid"]), 0)

        self.assertIn("card_removal_priority", data)
        self.assertGreater(len(data["card_removal_priority"]), 0)
        self.assertIn("Strike", data["card_removal_priority"][0]["card_name"])

    def test_analysis_caching(self):
        """Verify run state hash caching avoids redundant work."""
        res1 = self.engine.analyze_deck(self.mock_run)
        res2 = self.engine.analyze_deck(self.mock_run)
        self.assertEqual(res1["data"]["build_name"], res2["data"]["build_name"])

    def test_gemini_api_call_mocked(self):
        """Verify Gemini call parses structured response properly."""
        mock_gemini_json = {
            "build_name": "Strength-Scaling Heavy Burst",
            "build_stage": "Core Engine Forming",
            "core_win_condition": "Scale Strength via Inflame and execute high damage turns.",
            "playbook": {
                "turn_1_2_priority": "Play Inflame as soon as drawn.",
                "key_sequencing": ["Play Bash before Attacks."],
                "mitigation_rule": "Take 4 chip damage if it lands Inflame."
            },
            "what_to_look_for": {
                "priority_cards": [{"card_name": "Twin Strike", "why": "Scales 2x with Strength"}],
                "priority_relics": [{"relic_name": "Akabeko", "why": "First turn burst"}],
                "priority_potions": [{"potion_name": "Strength Potion", "why": "Boss boost"}]
            },
            "what_to_avoid": [{"target": "Snecko Eye", "danger_reason": "Low cost deck"}],
            "card_removal_priority": [{"card_name": "Strike", "reason": "Weak starter"}],
            "boss_matchup": {"threat_assessment": "Needs more block."}
        }

        with patch("sts2_companion.advisor.deck_engine.get_gemini_api_key", return_value="fake_key"):
            with patch.object(self.engine, "call_gemini", return_value={"success": True, "model": "gemini-2.5-flash", "data": mock_gemini_json}):
                res = self.engine.analyze_deck(self.mock_run, force_refresh=True)
                self.assertTrue(res["success"])
                self.assertEqual(res["provider"], "gemini")
                self.assertEqual(res["data"]["build_name"], "Strength-Scaling Heavy Burst")

    def test_deck_chat_mocked(self):
        """Verify deck chat provides direct strategic answers."""
        with patch("sts2_companion.advisor.deck_engine.get_gemini_api_key", return_value="fake_key"):
            with patch("requests.post") as mock_post:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "candidates": [{
                        "content": {
                            "parts": [{"text": "You should remove a Strike at the next shop to increase the odds of drawing Inflame on turn 1."}]
                        }
                    }]
                }
                mock_post.return_value = mock_resp

                res = self.engine.chat_about_deck("What should I remove at the next shop?", self.mock_run)
                self.assertTrue(res["success"])
                self.assertIn("remove a Strike", res["reply"])


if __name__ == "__main__":
    unittest.main()
