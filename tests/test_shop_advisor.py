"""
Unit tests for STS2 Shop & Merchant Advisor.
"""

import json
import unittest
from unittest.mock import patch, MagicMock

from sts2_companion.advisor.shop_advisor import STS2ShopAdvisor
from sts2_companion.web.app import create_app


class TestShopAdvisor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("data/sts2_cards.json", "r", encoding="utf-8") as f:
            cls.cards_db = json.load(f)
        with open("data/sts2_relics.json", "r", encoding="utf-8") as f:
            cls.relics_db = json.load(f)
        with open("data/sts2_potions.json", "r", encoding="utf-8") as f:
            cls.potions_db = json.load(f)

        cls.advisor = STS2ShopAdvisor(cls.cards_db, cls.relics_db, cls.potions_db)
        cls.app = create_app()
        cls.client = cls.app.test_client()

        cls.starter_run = {
            "character": "Ironclad",
            "current_floor": 6,
            "current_act": 1,
            "gold": 210,
            "deck": [
                {"id": "CARD.STRIKE_IRONCLAD", "name": "Strike", "card_type": "Attack"},
                {"id": "CARD.STRIKE_IRONCLAD", "name": "Strike", "card_type": "Attack"},
                {"id": "CARD.STRIKE_IRONCLAD", "name": "Strike", "card_type": "Attack"},
                {"id": "CARD.STRIKE_IRONCLAD", "name": "Strike", "card_type": "Attack"},
                {"id": "CARD.STRIKE_IRONCLAD", "name": "Strike", "card_type": "Attack"},
                {"id": "CARD.DEFEND_IRONCLAD", "name": "Defend", "card_type": "Skill"},
                {"id": "CARD.DEFEND_IRONCLAD", "name": "Defend", "card_type": "Skill"},
                {"id": "CARD.DEFEND_IRONCLAD", "name": "Defend", "card_type": "Skill"},
                {"id": "CARD.DEFEND_IRONCLAD", "name": "Defend", "card_type": "Skill"},
                {"id": "CARD.BASH", "name": "Bash", "card_type": "Attack"},
                {"id": "CARD.POMMEL_STRIKE", "name": "Pommel Strike", "card_type": "Attack"},
            ],
            "relics": [
                {"id": "RELIC.BURNING_BLOOD", "name": "Burning Blood"}
            ],
            "potions": []
        }

    def test_purge_evaluation_with_curses(self):
        """Curse removal should be scored with MUST BUY priority."""
        curse_run = dict(self.starter_run)
        curse_run["deck"] = list(self.starter_run["deck"]) + [
            {"id": "CARD.CLUMSY", "name": "Clumsy", "card_type": "Curse"}
        ]
        shop_data = {
            "gold": 200,
            "removal_cost": 75,
            "removal_available": True,
            "cards": [],
            "relics": [],
            "potions": []
        }
        res = self.advisor.evaluate_shop(shop_data, curse_run)
        purge = res.get("purge_evaluation", {})
        self.assertEqual(purge.get("target"), "Clumsy")
        self.assertEqual(purge.get("priority"), "MUST BUY")
        self.assertGreaterEqual(purge.get("score", 0), 9.0)

    def test_purge_evaluation_starter_attacks(self):
        """In Act 1 with 5 starter strikes, Strike removal should be recommended."""
        shop_data = {
            "gold": 150,
            "removal_cost": 75,
            "removal_available": True,
            "cards": [],
            "relics": [],
            "potions": []
        }
        res = self.advisor.evaluate_shop(shop_data, self.starter_run)
        purge = res.get("purge_evaluation", {})
        self.assertIn("Strike", purge.get("target", ""))
        self.assertIn(purge.get("priority"), ["STRONG VALUE", "MUST BUY"])

    def test_knapsack_purchase_baskets_budget_cap(self):
        """Baskets must strictly not exceed the player's available gold budget."""
        shop_data = {
            "gold": 210,
            "removal_cost": 75,
            "removal_available": True,
            "cards": [
                {"name": "Shockwave", "price": 68},
                {"name": "Impervious", "price": 140},
                {"name": "Whirlwind", "price": 75},
            ],
            "relics": [
                {"name": "Vajra", "price": 160},
                {"name": "Anchor", "price": 150},
            ],
            "potions": [
                {"name": "Fire Potion", "price": 50},
            ]
        }
        res = self.advisor.evaluate_shop(shop_data, self.starter_run)
        baskets = res.get("baskets", [])
        self.assertGreater(len(baskets), 0)

        for b in baskets:
            self.assertLessEqual(b["total_spent"], 210)
            self.assertEqual(b["gold_remaining"], 210 - b["total_spent"])
            self.assertGreater(len(b["items"]), 0)

    def test_low_gold_budget_handling(self):
        """When gold is lower than removal and relics, affordable potions or cheap cards are prioritized."""
        shop_data = {
            "gold": 55,
            "removal_cost": 75,
            "removal_available": True,
            "cards": [
                {"name": "Shockwave", "price": 68},
            ],
            "relics": [
                {"name": "Vajra", "price": 160},
            ],
            "potions": [
                {"name": "Block Potion", "price": 50},
            ]
        }
        res = self.advisor.evaluate_shop(shop_data, self.starter_run)
        baskets = res.get("baskets", [])
        self.assertGreater(len(baskets), 0)
        basket_items = baskets[0]["items"]
        self.assertEqual(len(basket_items), 1)
        self.assertEqual(basket_items[0]["name"], "Block Potion")
        self.assertLessEqual(baskets[0]["total_spent"], 55)

    def test_api_shop_advise_endpoint(self):
        """Test POST /api/shop_advise returns valid recommendations."""
        payload = {
            "gold": 250,
            "removal_cost": 75,
            "removal_available": True,
            "cards": [{"name": "Shockwave", "price": 68}],
            "relics": [{"name": "Vajra", "price": 160}],
            "potions": [{"name": "Fire Potion", "price": 50}]
        }
        resp = self.client.post("/api/shop_advise", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("baskets", data)
        self.assertIn("purge_evaluation", data)
        self.assertIn("ranked_items", data)
        self.assertIn("gemini_advice", data)

    def test_api_potions_catalog(self):
        """Test GET /api/potions returns potions database list."""
        resp = self.client.get("/api/potions")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        first_pot = data[0]
        self.assertIn("name", first_pot)
        self.assertIn("description", first_pot)


if __name__ == "__main__":
    unittest.main()
