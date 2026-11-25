import json
import unittest
from unittest.mock import Mock, patch

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError

from agentic_flow.goals import node, prompt
from agentic_flow.goals.graph import build_goals
from agentic_flow.state import RED_FLAG


def goal(**changes):
    return {
        "statement": "Reduce progress enquiries to less than one hour per week.",
        "actors": [], "goal_type": "hard", "resources": [], "plans": "",
        "justification": "", **changes,
    }


def actor(stakeholder_id, **changes):
    return {
        "name": "Repair coordinators", "stakeholder_id": stakeholder_id,
        "role": "Coordinator", "involvement": "Spend less time answering enquiries.",
        **changes,
    }


class GoalFlowTests(unittest.TestCase):
    def setUp(self):
        self.extractor = Mock()
        patcher = patch.object(node, "goal_extractor", self.extractor)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.graph = build_goals(InMemorySaver())
        self.config = {"configurable": {"thread_id": self.id()}}
        self.state = {
            "prd": "Coordinators want to spend less than one hour per week on enquiries.",
            "captured_intent": {"single_statement_intent": "Coordinate repairs."},
            "stakeholder_metadata": {"instructions": "", "stakeholders": [{
                "stakeholder_id": "Stakeholder-1", "name": "Repair coordinators",
                "involvement": "direct", "summary": "Assign repair jobs.",
                "justification": "Know the repair workflow.",
            }]},
            "persona_metadata": {"instructions": "", "personas": [{
                "persona_id": "Persona-1", "stakeholder_id": None, "name": "Morgan",
                "role": "", "status_and_trust_level": "", "demographics": "",
                "ksa": "", "gmc": "Distinguish current and completed work.",
                "usage_patterns": "Check summaries each morning.",
            }]},
        }

    def test_extracts_all_goals_and_checkpoints_without_user_interaction(self):
        self.extractor.invoke.return_value = {"goals": [
            goal(actors=[actor("Stakeholder-1"), actor("Stakeholder-999"),
                         actor(None, name="Notification subsystem", role="", involvement="")]),
            goal(statement="Make repair progress easy to understand.", goal_type="soft"),
            goal(statement="Improve the repair process.", goal_type=None),
        ]}
        result = self.graph.invoke(self.state, self.config)
        records = result["goal_metadata"]["goals"]
        self.assertEqual([g["goal_id"] for g in records], ["Goal-1", "Goal-2", "Goal-3"])
        self.assertEqual([a["stakeholder_id"] for a in records[0]["actors"]],
                         ["Stakeholder-1", None, None])
        self.assertEqual(records[0]["actors"][2]["name"], "Notification subsystem")
        self.assertEqual(records[0]["actors"][0]["involvement"],
                         "Spend less time answering enquiries.")
        self.assertEqual(records[1]["goal_type"], "soft")
        self.assertIsNone(records[2]["goal_type"])
        self.assertEqual(records[1]["plans"], "")
        self.assertEqual(records[1]["resources"], [])
        self.assertNotIn("__interrupt__", result)
        for key, value in self.state.items():
            self.assertEqual(result[key], value)
        self.assertEqual(self.graph.get_state(self.config).values["goal_metadata"],
                         result["goal_metadata"])
        self.assertEqual(self.graph.get_state(self.config).next, ())
        self.extractor.invoke.assert_called_once()
        messages = self.extractor.invoke.call_args.args[0]
        self.assertIsInstance(messages[0], SystemMessage)
        self.assertEqual(messages[0].content, prompt.GOAL_EXTRACTION_INSTRUCTIONS)
        self.assertIsInstance(messages[1], HumanMessage)
        self.assertIn(self.state["prd"], messages[1].content)
        for value in (node.intent_context(self.state["captured_intent"]),
                      self.state["stakeholder_metadata"]["stakeholders"],
                      self.state["persona_metadata"]["personas"]):
            self.assertIn(json.dumps(value), messages[1].content)

    def test_quotes_are_checked_and_unsupported_goals_red_flagged(self):
        quote = "Coordinators want to spend less than one hour per week on enquiries."
        self.extractor.invoke.return_value = {"goals": [
            goal(source=quote),
            goal(statement="Delight every coordinator.", source="A sentence the PRD lacks."),
        ]}
        records = self.graph.invoke(self.state, self.config)["goal_metadata"]["goals"]
        self.assertEqual(records[0]["source"], quote)
        self.assertFalse(records[0]["statement"].startswith(RED_FLAG))
        self.assertIsNone(records[1]["source"])
        self.assertEqual(records[1]["statement"], f"{RED_FLAG} Delight every coordinator.")

    def test_benefit_links_are_kept_only_for_extracted_benefits(self):
        self.state["captured_intent"]["benefits"] = [
            {"id": "Benefit-1", "description": "Under an hour a week on enquiries.",
             "addresses": [], "measure": "under an hour", "kind": "hard", "source": None}]
        self.extractor.invoke.return_value = {"goals": [
            goal(benefit_ids=["Benefit-1", "Benefit-1", "Benefit-9"])]}
        result = self.graph.invoke(self.state, self.config)
        self.assertEqual(result["goal_metadata"]["goals"][0]["benefit_ids"], ["Benefit-1"])
        request = self.extractor.invoke.call_args.args[0][1].content
        self.assertIn('"id": "Benefit-1"', request)

    def test_intent_context_keeps_ids_and_drops_evaluation(self):
        context = node.intent_context({
            "single_statement_intent": f"{RED_FLAG} Coordinate repairs.",
            "sson_evaluation": {"score": 90},
            "problems": [{"id": "Problem-1", "description": f"{RED_FLAG} Slow.", "source": None}],
        })
        self.assertEqual(context, {"single_statement_of_need": "Coordinate repairs.",
                                   "problems": [{"id": "Problem-1", "description": "Slow."}]})

    def test_empty_goal_list_is_accepted(self):
        self.extractor.invoke.return_value = {"goals": []}
        result = self.graph.invoke(self.state, self.config)
        self.assertEqual(result["goal_metadata"]["goals"], [])

    def test_missing_upstream_context_keeps_extracted_goal_and_actor(self):
        self.extractor.invoke.return_value = {"goals": [goal(actors=[actor("Stakeholder-1")])]}
        result = self.graph.invoke({"prd": self.state["prd"]}, self.config)
        record = result["goal_metadata"]["goals"][0]
        self.assertIsNone(record["actors"][0]["stakeholder_id"])
        self.assertEqual(record["actors"][0]["name"], "Repair coordinators")

    def test_invalid_output_does_not_save_partial_goals(self):
        self.extractor.invoke.return_value = {"goals": [goal(), goal(goal_type="unsupported")]}
        with self.assertRaises(ValidationError):
            self.graph.invoke(self.state, self.config)
        self.assertEqual(self.graph.get_state(self.config).values["goal_metadata"]["goals"], [])

    def test_missing_or_blank_prd_fails_before_model_call(self):
        for state in ({}, {"prd": " "}, {"prd": None}):
            with self.subTest(state=state), self.assertRaisesRegex(ValueError, "non-empty PRD"):
                node.prepare_goal_request(state)
        self.extractor.invoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()
