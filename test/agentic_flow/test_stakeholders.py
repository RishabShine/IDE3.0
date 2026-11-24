import unittest
from unittest.mock import Mock, patch

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError

from agentic_flow.user_modelling.stakeholders.graph import build_stakeholders
from agentic_flow.user_modelling.stakeholders import node, prompt


class StakeHolderFlowTests(unittest.TestCase):
    def setUp(self):
        self.extractor = Mock()
        patcher = patch.object(node, "stakeholder_extractor", self.extractor)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.graph = build_stakeholders(InMemorySaver())
        self.config = {"configurable": {"thread_id": self.id()}}
        self.state = {"prd": "Dispatchers assign jobs.\nTechnicians perform the work."}

    def test_extracts_without_user_interrupt_and_checkpoints_string_ids(self):
        self.extractor.invoke.return_value = {"stakeholders": [
            {"name": "Dispatchers", "involvement": "direct",
             "summary": "Assign jobs.", "justification": "Inform job assignment."},
            {"name": "Technicians", "involvement": None,
             "summary": "Perform the work.", "justification": "Inform the work process."},
        ]}
        result = self.graph.invoke(self.state, self.config)
        self.assertNotIn("__interrupt__", result)
        records = result["stakeholder_metadata"]["stakeholders"]
        self.assertEqual([r["stakeholder_id"] for r in records],
                         ["Stakeholder-1", "Stakeholder-2"])
        self.assertIsNone(records[1]["involvement"])
        self.assertEqual(result["prd"], self.state["prd"])
        self.assertEqual(self.graph.get_state(self.config).values["stakeholder_metadata"],
                         result["stakeholder_metadata"])
        self.assertEqual(self.graph.get_state(self.config).next, ())
        self.extractor.invoke.assert_called_once()
        messages = self.extractor.invoke.call_args.args[0]
        self.assertIsInstance(messages[0], SystemMessage)
        self.assertEqual(messages[0].content, prompt.STAKEHOLDER_EXTRACTION_INSTRUCTIONS)
        self.assertIsInstance(messages[1], HumanMessage)
        self.assertIn(self.state["prd"], messages[1].content)
        self.assertIn("<derived_intent>\n{}\n</derived_intent>", messages[1].content)

    def test_no_supported_stakeholders_returns_empty_list(self):
        self.extractor.invoke.return_value = {"stakeholders": []}
        result = self.graph.invoke(self.state, self.config)
        self.assertEqual(result["stakeholder_metadata"]["stakeholders"], [])
        self.assertNotIn("__interrupt__", result)

    def test_missing_or_blank_prd_is_rejected_before_model_call(self):
        for state in ({}, {"prd": "  "}, {"prd": None}):
            with self.subTest(state=state):
                with self.assertRaisesRegex(ValueError, "non-empty PRD"):
                    node.prepare_stakeholder_request(state)
        self.extractor.invoke.assert_not_called()

    def test_invalid_output_does_not_save_partial_stakeholders(self):
        self.extractor.invoke.return_value = {"stakeholders": [
            {"name": "Dispatchers", "involvement": "direct",
             "summary": "Assign jobs.", "justification": "Inform assignment."},
            {"name": "Technicians", "involvement": "unsupported",
             "summary": "Perform work.", "justification": "Inform the work."},
        ]}
        with self.assertRaises(ValidationError):
            self.graph.invoke(self.state, self.config)
        metadata = self.graph.get_state(self.config).values["stakeholder_metadata"]
        self.assertEqual(metadata["stakeholders"], [])


if __name__ == "__main__":
    unittest.main()
