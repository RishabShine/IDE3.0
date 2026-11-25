import json
import unittest
from unittest.mock import Mock, patch

from langgraph.checkpoint.memory import InMemorySaver

from agentic_flow.artifact_graph.node import build_artifact_graph
from agentic_flow.use_cases import node
from agentic_flow.use_cases.graph import build_use_cases
from agentic_flow.use_cases.schema import UseCaseModelResponse


def response(**changes):
    return UseCaseModelResponse.model_validate({
        "system_name": "Room booking",
        "actors": [
            {"name": "Student", "kind": "human", "stakeholder_id": "Stakeholder-1"},
            {"name": "Front-desk staff", "kind": "human", "stakeholder_id": "Stakeholder-2"},
            {"name": "MacID service", "kind": "system", "stakeholder_id": None},
        ],
        "use_cases": [
            {"name": "Book room", "description": "A student books a room.",
             "primary_actor": "Student", "supporting_actors": ["MacID service"],
             "goal_ids": ["Goal-1"]},
            {"name": "Review bookings", "description": "Staff review the day's bookings.",
             "primary_actor": "front-desk  staff", "supporting_actors": [],
             "goal_ids": ["Goal-2"]},
        ],
        "relationships": [],
        **changes,
    })


STAKEHOLDERS = {"Stakeholder-1", "Stakeholder-2"}
GOALS = {"Goal-1", "Goal-2"}


class BuildModelTests(unittest.TestCase):
    def test_assigns_ids_and_resolves_names_to_ids(self):
        model = node.build_model(response(), STAKEHOLDERS, GOALS)
        self.assertEqual(model["system_name"], "Room booking")
        self.assertEqual([(a["actor_id"], a["name"], a["stakeholder_id"]) for a in model["actors"]],
                         [("Actor-1", "Student", "Stakeholder-1"),
                          ("Actor-2", "Front-desk staff", "Stakeholder-2"),
                          ("Actor-3", "MacID service", None)])
        first, second = model["use_cases"]
        self.assertEqual((first["use_case_id"], first["primary_actor_id"],
                          first["supporting_actor_ids"]), ("UC-1", "Actor-1", ["Actor-3"]))
        # names match ignoring case and spacing
        self.assertEqual(second["primary_actor_id"], "Actor-2")
        self.assertEqual(model["issues"], [])

    def test_unknown_links_are_removed_and_reported(self):
        model = node.build_model(response(
            actors=[{"name": "Student", "kind": "human", "stakeholder_id": "Stakeholder-9"}],
            use_cases=[{"name": "Book room", "description": "", "primary_actor": "Student",
                        "supporting_actors": ["Cleaner"], "goal_ids": ["Goal-1", "Goal-7"]},
                       {"name": "book ROOM", "description": "", "primary_actor": "Student",
                        "supporting_actors": [], "goal_ids": []}],
        ), STAKEHOLDERS, GOALS)
        self.assertIsNone(model["actors"][0]["stakeholder_id"])
        self.assertEqual(model["actors"][1]["name"], "Cleaner")  # added, not dropped
        self.assertEqual(model["use_cases"][0]["goal_ids"], ["Goal-1"])
        self.assertEqual(len(model["use_cases"]), 1)
        issues = " | ".join(model["issues"])
        for note in ("unknown stakeholder Stakeholder-9", "'Cleaner', which was not in the actor",
                     "unknown goal(s) Goal-7", "listed twice", "Goal-2 is achieved by no use case"):
            self.assertIn(note, issues)

    def test_relationships_are_resolved_and_checked(self):
        model = node.build_model(response(
            use_cases=[{"name": n, "description": "", "primary_actor": "Student",
                        "supporting_actors": [], "goal_ids": ["Goal-1", "Goal-2"]}
                       for n in ("Book room", "Pick room", "Pay fee", "Join waitlist")],
            relationships=[
                {"kind": "include", "source": "Book room", "target": "Pick room", "condition": "x"},
                {"kind": "include", "source": "Pick room", "target": "Pay fee", "condition": ""},
                {"kind": "include", "source": "Book room", "target": "Pick room", "condition": ""},
                {"kind": "extend", "source": "Join waitlist", "target": "Book room", "condition": ""},
                {"kind": "extend", "source": "Book room", "target": "Book room", "condition": "x"},
                {"kind": "include", "source": "Book room", "target": "Print ticket", "condition": ""},
            ],
        ), STAKEHOLDERS, GOALS)
        self.assertEqual(model["relationships"], [
            {"kind": "include", "source": "UC-1", "target": "UC-2", "condition": ""},
            {"kind": "include", "source": "UC-2", "target": "UC-3", "condition": ""},
            {"kind": "extend", "source": "UC-4", "target": "UC-1", "condition": ""},
        ])
        issues = " | ".join(model["issues"])
        self.assertIn("UC-1 → UC-2 → UC-3 chains «include»", issues)
        self.assertIn("UC-4 «extend» UC-1 states no condition", issues)
        self.assertIn("'Print ticket' names a use case that does not exist", issues)
        self.assertIn("Actor-2 (Front-desk staff) takes part in no use case", issues)


class UseCaseGraphTests(unittest.TestCase):
    def setUp(self):
        self.extractor = Mock()
        self.extractor.invoke.return_value = response().model_dump()
        patcher = patch.object(node, "use_case_extractor", self.extractor)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.state = {
            "prd": "Students book rooms. Staff review bookings.",
            "captured_intent": {"single_statement_intent": "Let students book rooms.",
                                "sson_evaluation": {"score": 90}},
            "stakeholder_metadata": {"instructions": "", "stakeholders": [
                {"stakeholder_id": s, "name": s, "involvement": "direct", "summary": "",
                 "justification": ""} for s in sorted(STAKEHOLDERS)]},
            "goal_metadata": {"instructions": "", "goals": [
                {"goal_id": g, "statement": f"🚩 {g} statement", "actors": [], "goal_type": "hard",
                 "resources": [], "plans": "", "justification": "", "source": None,
                 "benefit_ids": []} for g in sorted(GOALS)]},
        }

    def test_one_call_with_goals_and_trimmed_intent(self):
        result = build_use_cases(InMemorySaver()).invoke(
            self.state, {"configurable": {"thread_id": self.id()}})
        self.extractor.invoke.assert_called_once()
        request = self.extractor.invoke.call_args.args[0][1].content
        self.assertIn('"id": "Goal-1", "statement": "Goal-1 statement"', request)
        self.assertIn('"single_statement_of_need": "Let students book rooms."', request)
        self.assertNotIn("sson_evaluation", request)
        self.assertEqual(len(result["use_case_metadata"]["use_cases"]), 2)

    def test_missing_prd_fails_before_the_model_call(self):
        with self.assertRaisesRegex(ValueError, "non-empty PRD"):
            node.prepare_use_case_request({})
        self.extractor.invoke.assert_not_called()

    def test_use_cases_join_the_artifact_graph(self):
        result = build_use_cases().invoke(self.state)
        graph = build_artifact_graph(result)
        edges = {(e["source"], e["relation"], e["target"]) for e in graph["edges"]}
        self.assertIn(("UC-1", "achieves", "Goal-1"), edges)
        self.assertIn(("UC-1", "serves", "Stakeholder-1"), edges)
        self.assertIn(("UC-2", "serves", "Stakeholder-2"), edges)
        result["use_case_metadata"]["use_cases"][1]["goal_ids"] = []
        gaps = {(g["kind"], g["artifact_id"]) for g in build_artifact_graph(result)["gaps"]}
        self.assertIn(("goal_without_use_case", "Goal-2"), gaps)
        self.assertIn(("use_case_without_goal", "UC-2"), gaps)


class MainFlowTests(unittest.TestCase):
    def test_prd_runs_intent_user_modelling_goals_use_cases_then_trace(self):
        from agentic_flow.goals import node as goal_node
        from agentic_flow.graph import build_ide3_chat
        from agentic_flow.user_modelling.personas import node as persona_node
        from agentic_flow.user_modelling.stakeholders import node as stakeholder_node
        from test_capture_intent import PRD, patch_capture_intent

        stakeholders, personas, goals, use_cases = Mock(), Mock(), Mock(), Mock()
        stakeholders.invoke.return_value = {"stakeholders": [
            {"name": "Students", "involvement": "direct", "summary": "Book rooms.",
             "justification": "Main users."}]}
        personas.invoke.return_value = {"personas": []}
        goals.invoke.return_value = {"goals": [{
            "statement": "Cut staff time", "goal_type": "hard", "resources": [], "plans": "",
            "justification": "", "benefit_ids": ["Benefit-1"],
            "actors": [{"name": "Students", "stakeholder_id": "Stakeholder-1",
                        "role": "", "involvement": ""}]}]}
        use_cases.invoke.return_value = {
            "system_name": "Room booking",
            "actors": [{"name": "Student", "kind": "human", "stakeholder_id": "Stakeholder-1"}],
            "use_cases": [{"name": "Book room", "description": "", "primary_actor": "Student",
                           "supporting_actors": [], "goal_ids": ["Goal-1"]}],
            "relationships": []}
        graph = build_ide3_chat(InMemorySaver())
        config = {"configurable": {"thread_id": self.id()}}
        with patch_capture_intent(), \
                patch.object(stakeholder_node, "stakeholder_extractor", stakeholders), \
                patch.object(persona_node, "persona_extractor", personas), \
                patch.object(goal_node, "goal_extractor", goals), \
                patch.object(node, "use_case_extractor", use_cases):
            # the PRD is the only input: nothing in the flow asks a question
            result = graph.invoke({"prd": PRD}, config)

        self.assertNotIn("__interrupt__", result)
        self.assertEqual(graph.get_state(config).next, ())
        self.assertIn("Problem-1", stakeholders.invoke.call_args.args[0][1].content)
        self.assertIn('"stakeholder_id": "Stakeholder-1"',
                      goals.invoke.call_args.args[0][1].content)
        self.assertIn('"id": "Goal-1"', use_cases.invoke.call_args.args[0][1].content)
        self.assertNotIn("goal2story_metadata", result)
        edges = {(e["source"], e["relation"], e["target"])
                 for e in result["artifact_graph"]["edges"]}
        self.assertTrue({("UC-1", "achieves", "Goal-1"), ("UC-1", "serves", "Stakeholder-1"),
                         ("Goal-1", "delivers", "Benefit-1")} <= edges)


if __name__ == "__main__":
    unittest.main()
