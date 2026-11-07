import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from coach import AnthropicProvider, Coach, DEMO_CONCEPT, FakeProvider, MemoryStore
from guardrails import Mode, Slide, valid_citations


class CoachTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.coach = Coach(FakeProvider(), store=self.store)

    def send(self, message, concept=DEMO_CONCEPT):
        return self.coach.reply("student", "lecture", concept, message)

    def session(self, concept=DEMO_CONCEPT):
        return self.store.get("student", "lecture", concept)

    def test_three_distinct_attempts_and_answer_requests(self):
        self.assertEqual(self.send("I am lost")[0], Mode.GUIDE)
        self.assertEqual(self.send("Just give me the answer")[0], Mode.GUIDE)
        self.assertEqual(self.session().failed_attempts, 0)
        self.assertEqual(self.send("I think all variables change")[0], Mode.GUIDE)
        self.assertEqual(self.send("I think all variables change")[0], Mode.GUIDE)
        self.assertEqual(self.session().failed_attempts, 1)
        self.assertEqual(self.send("I think they are added")[0], Mode.GUIDE)
        mode, response = self.send("I think they disappear entirely")
        self.assertEqual(mode, Mode.EXPLAIN)
        self.assertIn("slide 9", response)
        self.assertFalse(self.session().gap_closed)
        self.send("I think other variables stay constant")
        self.assertTrue(self.session().gap_closed)

    def test_assessed_overrides_attempts_and_stays_locked(self):
        self.session().assessed = True
        for message in ("I'm lost", "I think everything changes", "I think we add inputs",
                        "I think we delete inputs", "give me the solution"):
            mode, response = self.send(message)
            self.assertEqual(mode, Mode.LOCKED)
            self.assertNotIn("held constant", response)
        self.assertEqual(self.session().failed_attempts, 3)

    def test_assessed_slide_locks_session_persistently(self):
        self.coach.search = lambda lecture, question: [Slide(9, "text", assessed=True)]
        self.assertEqual(self.send("Help")[0], Mode.LOCKED)
        self.coach.search = lambda lecture, question: [Slide(9, "text")]
        self.assertEqual(self.send("Help again")[0], Mode.LOCKED)

    def test_concepts_and_students_have_independent_state(self):
        self.send("Help")
        self.send("I think everything changes")
        self.assertEqual(self.session().failed_attempts, 1)
        self.assertEqual(self.send("Help", concept="integration")[0], Mode.GUIDE)
        self.assertEqual(self.session("integration").failed_attempts, 0)
        self.assertEqual(self.store.get("another", "lecture", DEMO_CONCEPT).failed_attempts, 0)

    def test_bad_citation_or_unsafe_output_falls_back(self):
        class Unsafe(FakeProvider):
            def tutor(self, mode, session, message, slides):
                return "The answer is 42 (slide 9)."

            def check_response(self, *args):
                return False

        coach = Coach(Unsafe())
        _, response = coach.reply("s", "l", DEMO_CONCEPT, "Help")
        self.assertNotIn("42", response)
        self.assertIn("slide 9", response)
        self.assertFalse(valid_citations("See slide 9 and slide 10", [Slide(9, "text")]))
        self.assertFalse(valid_citations("No citations", [Slide(9, "text")]))

    def test_no_slides_does_not_call_model(self):
        class NoCalls(FakeProvider):
            def tutor(self, *args):
                raise AssertionError("should not be called")

        coach = Coach(NoCalls(), search=lambda lecture, message: [])
        _, response = coach.reply("s", "l", DEMO_CONCEPT, "Help")
        self.assertIn("couldn't find", response)

    def test_anthropic_json_checks_disable_thinking(self):
        provider = AnthropicProvider.__new__(AnthropicProvider)
        provider.model = "test-model"
        provider.client = SimpleNamespace(messages=SimpleNamespace(create=Mock(
            return_value=SimpleNamespace(content=[SimpleNamespace(type="text", text='{"safe": true}')])
        )))

        self.assertEqual(provider._json("review", "response"), {"safe": True})
        kwargs = provider.client.messages.create.call_args.kwargs
        self.assertEqual(kwargs["thinking"], {"type": "disabled"})
        self.assertEqual(kwargs["max_tokens"], 200)


if __name__ == "__main__":
    unittest.main()
