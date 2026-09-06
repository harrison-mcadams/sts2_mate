"""
Comprehensive Verification Tests for Slay the Spire 2 Companion App.
"""

import json
import os
import unittest
from sts2_companion.core.extractor import STS2Extractor
from sts2_companion.core.save_parser import STS2SaveParser
from sts2_companion.core.miner import STS2HistoryMiner
from sts2_companion.advisor.evaluator import STS2CardRewardAdvisor
from sts2_companion.web.app import create_app


class TestSTS2Companion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_dir = "data"
        cls.parser = STS2SaveParser(data_dir=cls.data_dir)
        cls.miner = STS2HistoryMiner(data_dir=cls.data_dir)
        cls.player_stats = cls.miner.mine_all(force_refresh=False)
        cls.advisor = STS2CardRewardAdvisor(cls.parser.cards_db, cls.player_stats)
        cls.app = create_app(data_dir=cls.data_dir)
        cls.client = cls.app.test_client()

    def test_database_loaded(self):
        """Verify cards and relics exist in the in-house STS2 database."""
        self.assertGreater(len(self.parser.cards_db), 500, "Should have 500+ extracted STS2 cards")
        self.assertGreater(len(self.parser.relics_db), 200, "Should have 200+ extracted STS2 relics")
        # Check specific STS2 cards
        self.assertIn("CARD.BREAKTHROUGH", self.parser.cards_db)
        self.assertIn("CARD.SETUP_STRIKE", self.parser.cards_db)
        self.assertIn("CARD.AFTERLIFE", self.parser.cards_db)

    def test_history_miner(self):
        """Verify history miner mined all 233 player runs."""
        self.assertEqual(self.player_stats["total_runs"], 233)
        self.assertGreater(len(self.player_stats["characters"]), 3)
        self.assertIn("Ironclad", self.player_stats["characters"])
        self.assertIn("Silent", self.player_stats["characters"])
        self.assertIn("Necrobinder", self.player_stats["characters"])

    def test_card_reward_evaluator(self):
        """Verify card reward evaluation produces reasoned recommendations."""
        mock_run = {
            "current_floor": 4,
            "current_act": 1,
            "character": "Ironclad",
            "current_hp": 70,
            "max_hp": 80,
            "hp_percent": 87.5,
            "deck": [
                {"id": "CARD.STRIKE_IRONCLAD", "card_type": "Attack"},
                {"id": "CARD.DEFEND_IRONCLAD", "card_type": "Skill"},
            ],
            "relics": [{"id": "RELIC.BURNING_BLOOD"}],
        }
        offered = ["CARD.POMMEL_STRIKE", "CARD.BREAKTHROUGH", "CARD.DEFEND_IRONCLAD"]
        result = self.advisor.evaluate_reward(offered, mock_run)

        self.assertIn("verdict", result)
        self.assertIn("ranked_options", result)
        self.assertEqual(len(result["ranked_options"]), 3)
        self.assertFalse(result["should_skip"])
        # Top choice should be an attack in early act 1
        top_type = result["ranked_options"][0]["card"]["card_type"]
        self.assertEqual(top_type, "Attack")

    def test_skip_recommendation_when_bloated(self):
        """Verify skip is recommended when a large deck is offered low-value duplicate cards."""
        bloated_deck = [{"id": f"CARD.CARD_{i}", "card_type": "Attack"} for i in range(26)]
        mock_run = {
            "current_floor": 35,
            "current_act": 3,
            "character": "Ironclad",
            "current_hp": 75,
            "max_hp": 80,
            "hp_percent": 93.7,
            "deck": bloated_deck,
            "relics": [],
        }
        # Low value basic attacks
        offered = ["CARD.STRIKE_IRONCLAD"]
        result = self.advisor.evaluate_reward(offered, mock_run)
        self.assertTrue(result["should_skip"], "Should recommend skip on bloated deck with weak offer")

    def test_api_endpoints(self):
        """Verify companion server API endpoints."""
        res = self.client.get("/api/state")
        self.assertEqual(res.status_code, 200)

        res = self.client.get("/api/cards?q=strike")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertGreater(len(data), 0)

        res = self.client.get("/api/stats")
        self.assertEqual(res.status_code, 200)

        res = self.client.post("/api/advise", json={"cards": ["Breakthrough", "Pommel Strike", "Shrug It Off"]})
        self.assertEqual(res.status_code, 200)
        advice = res.get_json()
        self.assertIn("verdict", advice)
        self.assertEqual(len(advice["ranked_options"]), 3)

    def test_qualitative_synergy_and_role_audit(self):
        """Verify role audit, card combos, and relic combos."""
        mock_run = {
            "current_floor": 3,
            "current_act": 1,
            "character": "Ironclad",
            "current_hp": 65,
            "max_hp": 80,
            "hp_percent": 81.2,
            "deck": [
                {"id": "CARD.STRIKE_IRONCLAD", "name": "Strike", "card_type": "Attack"},
                {"id": "CARD.DEFEND_IRONCLAD", "name": "Defend", "card_type": "Skill"},
                {"id": "CARD.INFLAME", "name": "Inflame", "card_type": "Power"},
                {"id": "CARD.DISMANTLE", "name": "Dismantle", "card_type": "Attack"},
            ],
            "relics": [{"id": "RELIC.AKABEKO", "name": "Akabeko"}],
        }
        # Offered: Whirlwind (AOE), Twin Strike (multi-hit), Defend (basic skill)
        offered = ["CARD.WHIRLWIND", "CARD.TWIN_STRIKE", "CARD.DEFEND_IRONCLAD"]
        result = self.advisor.evaluate_reward(offered, mock_run)

        # Whirlwind should audit 0 AOE in deck and flag as critical gap
        ww_opt = next(o for o in result["ranked_options"] if o["card"]["id"] == "CARD.WHIRLWIND")
        self.assertEqual(ww_opt["tactical_fit"], "Fills Critical Gap")
        self.assertEqual(ww_opt["role_audit"]["current_count"], 0)
        self.assertTrue(ww_opt["role_audit"]["is_critical"])

        # Twin Strike should combo with Inflame (Strength) and Akabeko
        twin_opt = next(o for o in result["ranked_options"] if o["card"]["id"] == "CARD.TWIN_STRIKE")
        self.assertGreater(len(twin_opt["card_combos"]), 0)
        self.assertIn("Inflame", twin_opt["card_combos"][0]["partner"])
        self.assertGreater(len(twin_opt["relic_combos"]), 0)
        self.assertEqual(twin_opt["relic_combos"][0]["relic"], "Akabeko")

    def test_gemini_config_manager(self):
        """Verify configuration loading and saving."""
        from sts2_companion.core.config import load_config, save_config, get_gemini_model
        initial_cfg = load_config()
        self.assertIn("gemini_model", initial_cfg)

        save_config({"gemini_model": "gemini-3.8-flash", "enable_search_grounding": True})
        self.assertEqual(get_gemini_model(), "gemini-3.8-flash")

    def test_gemini_prompt_builder_and_guardrails(self):
        """Verify Gemini prompt contains authoritative STS2 ground-truth and anti-STS1 directives."""
        from sts2_companion.advisor.ai_advisor import GeminiSTS2Advisor
        ai_adv = GeminiSTS2Advisor(self.parser.cards_db, self.parser.relics_db, self.player_stats)

        mock_run = {
            "character": "Ironclad",
            "current_floor": 8,
            "current_act": 1,
            "ascension": 9,
            "current_hp": 61,
            "max_hp": 71,
            "gold": 208,
            "deck": [
                {"name": "Bash", "card_type": "Attack", "cost": 1},
                {"name": "Defend", "card_type": "Skill", "cost": 1},
            ],
            "relics": [{"name": "Burning Blood", "description": "Heal 6 HP at end of combat."}],
        }
        offered = [
            self.parser.get_card_info("CARD.SWORD_BOOMERANG"),
            self.parser.get_card_info("CARD.WHIRLWIND"),
            self.parser.get_card_info("CARD.BLUDGEON"),
        ]

        prompt = ai_adv.build_prompt(offered, mock_run)

        # Verify strict STS2 guardrails
        self.assertIn("Slay the Spire 2", prompt)
        self.assertIn("NEVER assume rules, card stats, or relic synergies from Slay the Spire 1", prompt)
        self.assertIn("Whirlwind", prompt)
        self.assertIn("Sword Boomerang", prompt)
        self.assertIn("Bludgeon", prompt)
        self.assertIn("Burning Blood", prompt)
        self.assertIn("Act 1", prompt)

    def test_gemini_ai_endpoints(self):
        """Verify /api/config and /api/ai_evaluate endpoints."""
        # GET /api/config
        res = self.client.get("/api/config")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("gemini_api_key_configured", data)
        self.assertIn("gemini_model", data)

        # POST /api/config
        post_res = self.client.post("/api/config", json={"gemini_model": "gemini-3.8-flash"})
        self.assertEqual(post_res.status_code, 200)
        self.assertEqual(post_res.get_json()["config"]["gemini_model"], "gemini-3.8-flash")

        # POST /api/ai_evaluate without key returns requires_api_key: True and fallback
        ai_res = self.client.post("/api/ai_evaluate", json={"cards": ["Whirlwind", "Sword Boomerang", "Bludgeon"]})
        self.assertEqual(ai_res.status_code, 200)
        eval_data = ai_res.get_json()
        # In test environment without key, it should gracefully fall back
        if not eval_data.get("success"):
            self.assertTrue(eval_data.get("requires_api_key") or "error" in eval_data)
            self.assertIsNotNone(eval_data.get("fallback_evaluation"))

    def test_gemini_ai_chat_endpoint(self):
        """Verify POST /api/ai_chat validation and response handling."""
        # Bad request: empty message
        bad_res = self.client.post("/api/ai_chat", json={"message": ""})
        self.assertEqual(bad_res.status_code, 400)

        # Valid payload format
        res = self.client.post("/api/ai_chat", json={
            "message": "What if I take Bludgeon instead?",
            "cards": ["Sword Boomerang", "Whirlwind", "Bludgeon"],
            "initial_recommendation": {
                "recommended_card": "Whirlwind",
                "verdict": "Pick Whirlwind"
            }
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("success", data)
        if not data.get("success"):
            self.assertTrue(data.get("requires_key") or "error" in data)


if __name__ == "__main__":
    unittest.main()
