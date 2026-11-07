"""Stephanie's coach API tests, on the integrated backend (demo-slide path).

The real-slide path is tested in test_coach_integration.py.
"""

import os
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

import coach_api
from coach import FakeProvider


class CoachApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"LOSTPOINT_DB": os.path.join(self.tmp.name, "test.db")})
        env.start()
        self.addCleanup(env.stop)
        self.provider_patch = patch.object(coach_api, "get_provider", return_value=FakeProvider())
        self.provider_patch.start()
        self.addCleanup(self.provider_patch.stop)
        import main

        self.client = TestClient(main.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.session_id = str(uuid4())

    def send(self, message, slide_number=2, session_id=None):
        return self.client.post("/api/coach", json={
            "session_id": session_id or self.session_id,
            "slide_number": slide_number,
            "message": message,
        })

    def test_guidance_cites_demo_slide_and_attempts_persist(self):
        first = self.send("Help", slide_number=2)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["mode"], "GUIDE")
        self.assertEqual(first.json()["source"], "demo")
        self.assertIn("slide 2", first.json()["response"])

        self.assertEqual(self.send("I think all variables change").json()["wrong_attempts"], 1)
        self.assertEqual(self.send("I think they are added", slide_number=3).json()["wrong_attempts"], 2)
        third = self.send("I think they disappear entirely", slide_number=1).json()
        self.assertEqual(third["mode"], "EXPLAIN")
        self.assertIn("slide 1", third["response"])
        self.assertFalse(third["gap_closed"])

        correct = self.send("I think other variables stay constant").json()
        self.assertTrue(correct["gap_closed"])
        other = self.send("Help", session_id=str(uuid4())).json()
        self.assertEqual(other["wrong_attempts"], 0)
        self.assertEqual(other["mode"], "GUIDE")

    def test_bad_input_does_not_call_provider(self):
        for payload in (
            {"slide_number": 9, "message": "Help"},
            {"slide_number": 2, "message": "  "},
            {"slide_number": 2, "message": "Help", "assessed": False},
        ):
            with self.subTest(payload=payload):
                response = self.client.post("/api/coach", json={"session_id": self.session_id, **payload})
                self.assertEqual(response.status_code, 422)
        coach_api.get_provider.assert_not_called()

    def test_missing_api_configuration_is_reported_without_exposing_details(self):
        coach_api.get_provider.side_effect = ValueError("secret should not appear")
        response = self.send("Help")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret", response.text)
        self.assertEqual(self.client.get("/api/health").json()["status"], "ok")


if __name__ == "__main__":
    unittest.main()
