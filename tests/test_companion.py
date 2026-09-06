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


if __name__ == "__main__":
    unittest.main()
