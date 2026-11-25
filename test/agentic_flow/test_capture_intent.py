import unittest
from unittest.mock import Mock, patch

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError

from agentic_flow.capture_intent import node, prompts
from agentic_flow.capture_intent.graph import build_capture_intent


class IntentFlowTests(unittest.TestCase):
    def setUp(self):
        self.extractor = Mock()
        patcher = patch.object(node, "intent_extractor", self.extractor)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.graph = build_capture_intent(InMemorySaver())
        self.config = {"configurable": {"thread_id": self.id()}}
        self.state = {
            "prd": (
                "Students email the front desk to book study rooms. "
                "Staff spend six hours a week on booking emails."
            ),
        }

    def test_extracts_and_checkpoints_without_user_interaction(self):
        self.extractor.invoke.return_value = {
            "intent": {
                "single_statement_intent": (
                    "Let students book study rooms themselves so staff spend "
                    "less time on booking emails."
                ),
                "what": "book study rooms themselves",
                "how": "self-service booking from their phones",
                "why": "staff spend too long on booking emails",
                "success_measure": "staff spend under one hour a week on booking emails",
                "current_process": "Students email the front desk.",
                "problems": [
                    {"description": "Staff spend six hours a week on emails.",
                     "source": "Staff spend six hours a week on booking emails."},
                    {"description": "Rooms can be double booked.", "source": ""},
                ],
                "benefits": [
                    {"description": "Staff spend under one hour a week on emails.",
                     "source": "", "addresses": [1], "measure": "under one hour a week",
                     "kind": "hard"},
                    {"description": "No double bookings.", "source": "",
                     "addresses": [2, 9], "measure": "", "kind": None},
                ],
                "goals": ["Cut staff time on bookings to under 1 hour per week."],
            }
        }

        result = self.graph.invoke(self.state, self.config)

        self.assertNotIn("__interrupt__", result)
        captured = result["captured_intent"]
        self.assertEqual(
            captured["single_statement_intent"],
            "Let students book study rooms themselves so staff spend less time on booking emails.",
        )
        self.assertEqual([p["id"] for p in captured["problems"]],
                         ["Problem-1", "Problem-2"])
        self.assertEqual(captured["benefits"][0]["addresses"], ["Problem-1"])
        self.assertEqual(captured["benefits"][1]["addresses"], ["Problem-2"])
        self.assertEqual(captured["goals"],
                         ["Cut staff time on bookings to under 1 hour per week."])
        self.assertEqual(result["intent_metadata"]["evaluation_of_statement"], "met")
        self.assertEqual(result["intent_metadata"]["attempt_number"], 1)
        self.assertNotIn("instructions", result["intent_metadata"])
        self.assertEqual(self.graph.get_state(self.config).next, ())

        self.extractor.invoke.assert_called_once()
        messages = self.extractor.invoke.call_args.args[0]
        self.assertIsInstance(messages[0], SystemMessage)
        self.assertEqual(messages[0].content, prompts.INTENT_EXTRACTION_INSTRUCTIONS)
        self.assertIsInstance(messages[1], HumanMessage)
        self.assertIn(self.state["prd"], messages[1].content)

    def test_empty_problems_and_benefits_are_accepted(self):
        self.extractor.invoke.return_value = {
            "intent": {
                "single_statement_intent": "Coordinate repairs online.",
                "problems": [],
                "benefits": [],
                "goals": [],
            }
        }
        result = self.graph.invoke(self.state, self.config)
        self.assertEqual(result["captured_intent"]["problems"], [])
        self.assertEqual(result["captured_intent"]["benefits"], [])
        self.assertEqual(result["captured_intent"]["goals"], [])

    def test_missing_or_blank_prd_fails_before_model_call(self):
        for state in ({}, {"prd": "  "}, {"prd": None}):
            with self.subTest(state=state):
                with self.assertRaisesRegex(ValueError, "non-empty PRD"):
                    node.prepare_intent_request(state)
        self.extractor.invoke.assert_not_called()

    def test_invalid_output_does_not_save_partial_intent(self):
        self.extractor.invoke.return_value = {
            "intent": {
                "single_statement_intent": "Coordinate repairs.",
                "benefits": [
                    {"description": "Faster repairs", "addresses": "Problem-1"},
                ],
            }
        }
        with self.assertRaises(ValidationError):
            self.graph.invoke(self.state, self.config)
        values = self.graph.get_state(self.config).values
        self.assertEqual(values["intent_metadata"]["single_statement_intent"], "")
        self.assertNotIn("captured_intent", values)


if __name__ == "__main__":
    unittest.main()
