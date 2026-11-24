import json
import unittest
from unittest.mock import Mock, patch

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError

from agentic_flow.user_modelling.graph import build_user_modelling
from agentic_flow.user_modelling.personas import node, prompt
from agentic_flow.user_modelling.personas.graph import build_personas
from agentic_flow.user_modelling.stakeholders import node as stakeholder_node


def profile(stakeholder_id=None, **changes):
    return {
        "stakeholder_id": stakeholder_id,
        "name": "", "role": "Repair coordinators",
        "status_and_trust_level": "", "demographics": "", "ksa": "",
        "gmc": "Avoid duplicate assignments.", "usage_patterns": "Assign repair jobs.",
        **changes,
    }


class PersonaFlowTests(unittest.TestCase):
    def setUp(self):
        self.extractor = Mock()
        patcher = patch.object(node, "persona_extractor", self.extractor)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.graph = build_personas(InMemorySaver())
        self.config = {"configurable": {"thread_id": self.id()}}
        self.stakeholders = [{
            "stakeholder_id": "Stakeholder-1", "name": "Repair coordinators",
            "involvement": "direct", "summary": "Assign jobs.",
            "justification": "Inform assignment rules.",
        }]
        self.state = {
            "prd": "Repair coordinators assign jobs and want to avoid duplicate assignments.",
            "captured_intent": {"single_statement_intent": "Coordinate repairs."},
            "stakeholder_metadata": {"instructions": "", "stakeholders": self.stakeholders},
        }

    def test_extracts_and_checkpoints_profiles_without_forcing_links(self):
        self.extractor.invoke.return_value = {"personas": [
            profile("Stakeholder-1"), profile(None), profile("Stakeholder-999"),
        ]}
        result = self.graph.invoke(self.state, self.config)
        self.assertNotIn("__interrupt__", result)
        records = result["persona_metadata"]["personas"]
        self.assertEqual([p["persona_id"] for p in records],
                         ["Persona-1", "Persona-2", "Persona-3"])
        self.assertEqual([p["stakeholder_id"] for p in records],
                         ["Stakeholder-1", None, None])
        self.assertEqual(records[0]["name"], "")
        self.assertEqual(records[0]["demographics"], "")
        self.assertEqual(result["stakeholder_metadata"], self.state["stakeholder_metadata"])
        self.assertEqual(self.graph.get_state(self.config).values["persona_metadata"],
                         result["persona_metadata"])
        self.extractor.invoke.assert_called_once()
        messages = self.extractor.invoke.call_args.args[0]
        self.assertIsInstance(messages[0], SystemMessage)
        self.assertEqual(messages[0].content, prompt.PERSONA_EXTRACTION_INSTRUCTIONS)
        self.assertIsInstance(messages[1], HumanMessage)
        self.assertIn(self.state["prd"], messages[1].content)
        self.assertIn(json.dumps(self.stakeholders), messages[1].content)
        self.assertIn(json.dumps(self.state["captured_intent"]), messages[1].content)

    def test_extracts_unlinked_profiles_without_a_stakeholder_list(self):
        self.extractor.invoke.return_value = {"personas": [profile("Stakeholder-1")]}
        result = self.graph.invoke({"prd": self.state["prd"]}, self.config)
        self.assertIsNone(result["persona_metadata"]["personas"][0]["stakeholder_id"])

    def test_invalid_output_does_not_save_partial_personas(self):
        self.extractor.invoke.return_value = {"personas": [profile(), profile(role=[])]}
        with self.assertRaises(ValidationError):
            self.graph.invoke(self.state, self.config)
        self.assertEqual(self.graph.get_state(self.config).values["persona_metadata"]["personas"], [])

    def test_missing_or_blank_prd_fails_before_model_call(self):
        for state in ({}, {"prd": " "}, {"prd": None}):
            with self.subTest(state=state), self.assertRaisesRegex(ValueError, "non-empty PRD"):
                node.prepare_persona_request(state)
        self.extractor.invoke.assert_not_called()

    def test_user_modelling_passes_extracted_stakeholders_to_personas(self):
        stakeholder_extractor = Mock()
        stakeholder_extractor.invoke.return_value = {"stakeholders": [
            {k: v for k, v in self.stakeholders[0].items() if k != "stakeholder_id"}
        ]}
        self.extractor.invoke.return_value = {"personas": []}
        with patch.object(stakeholder_node, "stakeholder_extractor", stakeholder_extractor):
            result = build_user_modelling().invoke({
                "prd": self.state["prd"], "captured_intent": self.state["captured_intent"],
            })
        self.assertEqual(result["persona_metadata"]["personas"], [])
        self.assertIn(json.dumps(result["stakeholder_metadata"]["stakeholders"]),
                      self.extractor.invoke.call_args.args[0][1].content)
        self.assertIn(json.dumps(self.state["captured_intent"]),
                      stakeholder_extractor.invoke.call_args.args[0][1].content)
        stakeholder_extractor.invoke.assert_called_once()
        self.extractor.invoke.assert_called_once()
        self.assertNotIn("__interrupt__", result)


if __name__ == "__main__":
    unittest.main()
