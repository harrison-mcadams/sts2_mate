"""
Unit tests for STS2 Boss Reward Advisor.
"""

import json
import unittest
from unittest.mock import patch, MagicMock

from sts2_companion.advisor.boss_advisor import STS2BossRewardAdvisor
from sts2_companion.web.app import create_app


class TestBossAdvisor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("data/sts2_cards.json", "r", encoding="utf-8") as f:
            cls.cards_db = json.load(f)
        with open("data/sts2_relics.json", "r", encoding="utf-8") as f:
            cls.relics_db = json.load(f)

        cls.advisor = STS2BossRewardAdvisor(cls.cards_db, cls.relics_db)
        cls.app = create_app()
        cls.client = cls.app.test_client()

        # Heavy high-cost deck
        cls.heavy_deck_run = {
            "character": "Ironclad",
            "current_floor": 16,
            "current_act": 1,
            "current_hp": 72,
            "max_hp": 80,
            "deck": [
                {"name": "Bash", "cost": 2},
                {"name": "Carnage", "cost": 2},
                {"name": "Heavy Blade", "cost": 2},
                {"name": "Impervious", "cost": 2},
                {"name": "Strike", "cost": 1},
                {"name": "Defend", "cost": 1},
            ],
            "relics": [
                {"name": "Burning Blood"}
            ]
        }

        # Rapid-cycle 0-cost spam deck
        cls.spam_deck_run = {
            "character": "Ironclad",
            "current_floor": 16,
            "current_act": 1,
            "current_hp": 55,
            "max_hp": 80,
            "deck": [
                {"name": "Anger", "cost": 0},
                {"name": "Anger", "cost": 0},
                {"name": "Pommel Strike", "cost": 1},
                {"name": "Dropkick", "cost": 1},
                {"name": "Strike", "cost": 1},
                {"name": "Defend", "cost": 1},
            ],
            "relics": []
        }

    def test_energy_demand_calculation(self):
        """Energy profile accurately flags energy hungry decks."""
        profile_heavy = self.advisor.analyze_deck_energy_profile(self.heavy_deck_run["deck"])
        self.assertTrue(profile_heavy["energy_hungry"])
        self.assertGreaterEqual(profile_heavy["high_cost_count"], 3)

        profile_spam = self.advisor.analyze_deck_energy_profile(self.spam_deck_run["deck"])
        self.assertFalse(profile_spam["energy_hungry"])
        self.assertGreaterEqual(profile_spam["zero_cost_count"], 2)

    def test_velvet_choker_trap_detection(self):
        """Velvet Choker is flagged as a TRAP on spam decks, but EXCELLENT on heavy decks."""
        # On spam deck
        res_spam = self.advisor.evaluate_boss_relic(
            "Velvet Choker",
            self.spam_deck_run["deck"],
            self.spam_deck_run["relics"],
            55, 80, 1
        )
        self.assertEqual(res_spam["priority"], "TRAP / DO NOT PICK")
        self.assertIn("LETHAL", res_spam["drawback_risk"])

        # On heavy deck
        res_heavy = self.advisor.evaluate_boss_relic(
            "Velvet Choker",
            self.heavy_deck_run["deck"],
            self.heavy_deck_run["relics"],
            72, 80, 1
        )
        self.assertEqual(res_heavy["priority"], "EXCELLENT")
        self.assertEqual(res_heavy["drawback_risk"], "LOW")

    def test_coffee_dripper_sustain_check(self):
        """Coffee Dripper with Burning Blood sustain scores high; without sustain and low HP scores risky."""
        # With Burning Blood sustain
        res_sustain = self.advisor.evaluate_boss_relic(
            "Coffee Dripper",
            self.heavy_deck_run["deck"],
            [{"name": "Burning Blood"}],
            72, 80, 1
        )
        self.assertEqual(res_sustain["priority"], "EXCELLENT")
        self.assertGreaterEqual(res_sustain["score"], 9.0)

        # Without sustain and low HP
        res_no_sustain = self.advisor.evaluate_boss_relic(
            "Coffee Dripper",
            self.heavy_deck_run["deck"],
            [],
            20, 80, 1
        )
        self.assertEqual(res_no_sustain["priority"], "RISKY")
        self.assertEqual(res_no_sustain["drawback_risk"], "HIGH")

    def test_evaluate_boss_rewards_ranking(self):
        """Evaluating 3 relics properly ranks them and identifies recommended pick."""
        offered = ["Velvet Choker", "Cursed Key", "Astrolabe"]
        res = self.advisor.evaluate_boss_rewards(offered, self.spam_deck_run)
        self.assertIn("recommended", res)
        self.assertIn("ranked_choices", res)
        self.assertEqual(len(res["ranked_choices"]), 3)

        # Velvet choker should NOT be the recommended pick on spam deck
        self.assertNotEqual(res["recommended"]["name"], "Velvet Choker")
        self.assertIn("WARNING", res["verdict"])

    def test_api_boss_advise_endpoint(self):
        """POST /api/boss_advise returns complete evaluation payload."""
        payload = {
            "relics": ["Cursed Key", "Astrolabe", "Coffee Dripper"]
        }
        resp = self.client.post("/api/boss_advise", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("recommended", data)
        self.assertIn("ranked_choices", data)
        self.assertIn("verdict", data)


if __name__ == "__main__":
    unittest.main()
