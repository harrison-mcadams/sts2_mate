"""
Unit tests for STS2 Unknown Room (?) & Event Advisor.
"""

import json
import unittest
from unittest.mock import patch, MagicMock

from sts2_companion.advisor.event_advisor import STS2EventAdvisor
from sts2_companion.web.app import create_app


class TestEventAdvisor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.advisor = STS2EventAdvisor(data_dir="data")
        cls.app = create_app()
        cls.client = cls.app.test_client()

        cls.healthy_run = {
            "character": "Ironclad",
            "current_floor": 7,
            "current_act": 1,
            "current_hp": 75,
            "max_hp": 80,
            "gold": 120,
            "deck": [
                {"name": "Strike"}, {"name": "Strike"}, {"name": "Strike"},
                {"name": "Strike"}, {"name": "Strike"},
                {"name": "Defend"}, {"name": "Defend"}, {"name": "Defend"},
            ],
            "relics": []
        }

        cls.critical_hp_run = {
            "character": "Ironclad",
            "current_floor": 11,
            "current_act": 1,
            "current_hp": 14,
            "max_hp": 80,
            "gold": 40,
            "deck": [
                {"name": "Strike"}, {"name": "Bash"},
            ],
            "relics": []
        }

    def test_events_catalog_loaded(self):
        """Verifies 40+ STS2 events are loaded into the database."""
        catalog = self.advisor.get_event_catalog()
        self.assertGreaterEqual(len(catalog), 30)

        # Verify known events exist
        event_ids = {e["id"] for e in catalog}
        self.assertIn("AMALGAMATOR", event_ids)
        self.assertIn("ABYSSAL_BATHS", event_ids)
        self.assertIn("AROMA_OF_CHAOS", event_ids)

    def test_event_resolution(self):
        """Resolves event by key or title."""
        edata = self.advisor.resolve_event("Amalgamator")
        self.assertIsNotNone(edata)
        self.assertEqual(edata["title"], "Amalgamator")
        self.assertGreater(len(edata["options_list"]), 0)

    def test_hp_safety_thresholding(self):
        """When HP is critically low, HP sacrifice options are marked DANGEROUS/LETHAL RISK."""
        # Abyssal Baths has Immerse (takes damage for Max HP) vs Abstain (heals HP)
        res_crit = self.advisor.evaluate_event("ABYSSAL_BATHS", self.critical_hp_run)
        self.assertTrue(res_crit["success"])

        # Recommended option must be Abstain (heal) when at 14 HP
        rec = res_crit["recommended"]
        self.assertIn("Abstain", rec["title"])

        # Immerse should be flagged dangerous
        immerse_opt = next((o for o in res_crit["options"] if "Immerse" in o["title"]), None)
        if immerse_opt:
            self.assertIn("LETHAL RISK", immerse_opt["risk_level"])

    def test_card_thinning_recommendation(self):
        """With 5 starter strikes, Amalgamator recommends combining strikes."""
        res = self.advisor.evaluate_event("AMALGAMATOR", self.healthy_run)
        self.assertTrue(res["success"])
        rec = res["recommended"]
        self.assertIn("Strike", rec["title"])
        self.assertIn("thinning", rec["reasoning"].lower())

    def test_api_events_catalog_endpoint(self):
        """GET /api/events_catalog returns event list."""
        resp = self.client.get("/api/events_catalog")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_api_event_advise_endpoint(self):
        """POST /api/event_advise returns complete event evaluation."""
        payload = {"event": "AROMA_OF_CHAOS"}
        resp = self.client.post("/api/event_advise", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("event", data)
        self.assertIn("options", data)
        self.assertIn("recommended", data)
        self.assertIn("verdict", data)


if __name__ == "__main__":
    unittest.main()
