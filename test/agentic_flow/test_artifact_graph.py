import copy
import unittest
from unittest.mock import Mock, patch

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from agentic_flow.artifact_graph.graph import build_artifact_graph_step
from agentic_flow.artifact_graph.node import build_artifact_graph
from agentic_flow.state import AgentState
from agentic_flow.user_modelling.graph import build_user_modelling
from agentic_flow.user_modelling.personas import node as persona_node
from agentic_flow.user_modelling.stakeholders import node as stakeholder_node


def stakeholder(number, name, involvement="direct"):
    return {"stakeholder_id": f"Stakeholder-{number}", "name": name,
            "involvement": involvement, "summary": f"{name} summary.",
            "justification": f"{name} justification."}


def persona(number, stakeholder_id, name="", role="Students"):
    return {"persona_id": f"Persona-{number}", "stakeholder_id": stakeholder_id,
            "name": name, "role": role, "status_and_trust_level": "",
            "demographics": "", "ksa": "", "gmc": "", "usage_patterns": ""}


def library_state():
    """Study-room booking example: every artifact is linked, so no gaps."""
    return {
        "prd": "Library Group Study-Room Booking ...",
        "captured_intent": {
            "single_statement_intent": "Let students book study rooms themselves.",
            "why": "Staff spend hours on bookings.",
            "problems": [
                {"id": "Problem-1", "description": "Staff spend 6 hours a week on emails."},
                {"id": "Problem-2", "description": "Rooms get double booked."},
            ],
            "benefits": [
                {"id": "Benefit-1", "description": "Under 1 hour a week on emails.",
                 "addresses": ["Problem-1"]},
                {"id": "Benefit-2", "description": "No room is double booked.",
                 "addresses": ["Problem-2"]},
            ],
        },
        "stakeholder_metadata": {"instructions": "", "stakeholders": [
            stakeholder(1, "Students"),
            stakeholder(2, "Front-desk staff"),
            stakeholder(3, "Library IT", involvement="indirect"),
        ]},
        "persona_metadata": {"instructions": "", "personas": [
            persona(1, "Stakeholder-1", name="Priya"),
            persona(2, "Stakeholder-2", role="Front-desk staff"),
        ]},
        "goal_metadata": {"instructions": "", "goals": [
            goal(1, benefit_ids=["Benefit-1", "Benefit-2"],
                 actors=[{"name": "Front-desk staff", "stakeholder_id": "Stakeholder-2",
                          "role": "Booking admin", "involvement": "Stop handling emails."}]),
        ]},
        "use_case_metadata": {"instructions": "", "system_name": "Room booking", "issues": [],
            "actors": [{"actor_id": "Actor-1", "name": "Front-desk staff", "kind": "human",
                        "stakeholder_id": "Stakeholder-2"}],
            "use_cases": [{"use_case_id": "UC-1", "name": "Review bookings", "description": "",
                           "primary_actor_id": "Actor-1", "supporting_actor_ids": [],
                           "goal_ids": ["Goal-1"]}],
            "relationships": []},
    }


def goal(number, **changes):
    return {"goal_id": f"Goal-{number}", "statement": "Cut staff booking time.",
            "source": None, "benefit_ids": [], "actors": [], "goal_type": "hard",
            "resources": [], "plans": "", "justification": "", **changes}


def edge_set(graph):
    return {(e["source"], e["relation"], e["target"]) for e in graph["edges"]}


def gap_set(graph):
    return {(g["kind"], g["artifact_id"]) for g in graph["gaps"]}


class BuildArtifactGraphTests(unittest.TestCase):
    def test_complete_example_has_every_artifact_link_and_no_gaps(self):
        graph = build_artifact_graph(library_state())

        self.assertEqual(
            [(n["id"], n["type"]) for n in graph["nodes"]],
            [("Intent-1", "intent"), ("Problem-1", "problem"), ("Problem-2", "problem"),
             ("Benefit-1", "benefit"), ("Benefit-2", "benefit"),
             ("Stakeholder-1", "stakeholder"), ("Stakeholder-2", "stakeholder"),
             ("Stakeholder-3", "stakeholder"),
             ("Persona-1", "persona"), ("Persona-2", "persona"), ("Goal-1", "goal"),
             ("UC-1", "use_case")],
        )
        self.assertEqual(edge_set(graph), {
            ("Problem-1", "motivates", "Intent-1"),
            ("Problem-2", "motivates", "Intent-1"),
            ("Benefit-1", "realizes", "Intent-1"),
            ("Benefit-2", "realizes", "Intent-1"),
            ("Benefit-1", "addresses", "Problem-1"),
            ("Benefit-2", "addresses", "Problem-2"),
            ("Stakeholder-1", "concerned_with", "Intent-1"),
            ("Stakeholder-2", "concerned_with", "Intent-1"),
            ("Stakeholder-3", "concerned_with", "Intent-1"),
            ("Persona-1", "represents", "Stakeholder-1"),
            ("Persona-2", "represents", "Stakeholder-2"),
            ("Goal-1", "refines", "Intent-1"),
            ("Goal-1", "delivers", "Benefit-1"),
            ("Goal-1", "delivers", "Benefit-2"),
            ("Goal-1", "involves", "Stakeholder-2"),
            ("UC-1", "achieves", "Goal-1"),
            ("UC-1", "serves", "Stakeholder-2"),
        })
        self.assertEqual(len(graph["edges"]), len(edge_set(graph)), "no duplicate edges")
        self.assertEqual(graph["gaps"], [])

    def test_labels_and_data_come_from_the_extracted_records(self):
        nodes = {n["id"]: n for n in build_artifact_graph(library_state())["nodes"]}

        self.assertEqual(nodes["Intent-1"]["label"],
                         "Let students book study rooms themselves.")
        self.assertEqual(nodes["Intent-1"]["data"]["why"], "Staff spend hours on bookings.")
        self.assertNotIn("problems", nodes["Intent-1"]["data"])
        self.assertEqual(nodes["Stakeholder-3"]["data"]["involvement"], "indirect")
        self.assertNotIn("stakeholder_id", nodes["Stakeholder-3"]["data"])
        # a persona label falls back from name to role
        self.assertEqual(nodes["Persona-1"]["label"], "Priya")
        self.assertEqual(nodes["Persona-2"]["label"], "Front-desk staff")

    def test_input_state_is_not_modified(self):
        state = library_state()
        before = copy.deepcopy(state)
        build_artifact_graph(state)
        self.assertEqual(state, before)

    def test_empty_state_reports_each_missing_artifact_type(self):
        graph = build_artifact_graph({})
        self.assertEqual(graph["nodes"], [])
        self.assertEqual(graph["edges"], [])
        self.assertEqual(gap_set(graph), {("missing_artifacts", None)})
        self.assertEqual(
            [g["detail"] for g in graph["gaps"]],
            ["No intent artifacts were extracted.",
             "No stakeholder artifacts were extracted.",
             "No persona artifacts were extracted.",
             "No goal artifacts were extracted.",
             "No use_case artifacts were extracted."],
        )

    def test_blank_intent_counts_as_missing_and_stakeholders_stay_unlinked_to_it(self):
        state = library_state()
        state["captured_intent"] = {"single_statement_intent": "   "}
        graph = build_artifact_graph(state)

        self.assertIn(("missing_artifacts", None), gap_set(graph))
        self.assertFalse(any(n["type"] == "intent" for n in graph["nodes"]))
        self.assertFalse(any(e["relation"] == "concerned_with" for e in graph["edges"]))

    def test_reports_unconnected_persona_stakeholder_and_problem(self):
        state = library_state()
        state["persona_metadata"]["personas"] = [persona(1, None, name="Morgan")]
        state["captured_intent"]["benefits"] = []
        graph = build_artifact_graph(state)

        self.assertEqual(gap_set(graph), {
            ("unlinked_persona", "Persona-1"),
            ("stakeholder_without_persona", "Stakeholder-1"),
            ("stakeholder_without_persona", "Stakeholder-2"),
            ("unaddressed_problem", "Problem-1"),
            ("unaddressed_problem", "Problem-2"),
            ("dangling_link", "Goal-1"),  # its benefits are gone
        })
        # indirect stakeholders are not expected to have personas
        self.assertNotIn(("stakeholder_without_persona", "Stakeholder-3"), gap_set(graph))

    def test_link_to_unknown_artifact_is_dropped_and_reported(self):
        state = library_state()
        state["captured_intent"]["benefits"][0]["addresses"] = ["Problem-1", "Problem-9"]
        state["persona_metadata"]["personas"][1]["stakeholder_id"] = "Stakeholder-7"
        graph = build_artifact_graph(state)

        self.assertNotIn(("Benefit-1", "addresses", "Problem-9"), edge_set(graph))
        self.assertIn(("Benefit-1", "addresses", "Problem-1"), edge_set(graph))
        self.assertNotIn(("Persona-2", "represents", "Stakeholder-7"), edge_set(graph))
        self.assertTrue({("dangling_link", "Benefit-1"), ("dangling_link", "Persona-2"),
                         ("unlinked_persona", "Persona-2")} <= gap_set(graph))
        dangling = [g["detail"] for g in graph["gaps"] if g["kind"] == "dangling_link"]
        self.assertIn("Problem-9 does not exist", dangling[0])

    def test_goal_gaps_unlinked_goal_and_benefit_without_goal(self):
        state = library_state()
        state["goal_metadata"]["goals"] = [
            goal(1, benefit_ids=["Benefit-1"]),
            goal(2, statement="Make booking pleasant.", goal_type="soft",
                 actors=[{"name": "A booking bot", "stakeholder_id": None,
                          "role": "", "involvement": ""}]),
        ]
        graph = build_artifact_graph(state)

        self.assertIn(("Goal-1", "delivers", "Benefit-1"), edge_set(graph))
        self.assertIn(("Goal-2", "refines", "Intent-1"), edge_set(graph))
        self.assertFalse(any(e["source"] == "Goal-2" and e["relation"] == "involves"
                             for e in graph["edges"]))
        self.assertEqual({g for g in gap_set(graph) if g[1] and g[1].startswith(("Goal", "Benefit"))},
                         {("unlinked_goal", "Goal-2"), ("benefit_without_goal", "Benefit-2"),
                          # one artifact can have several gaps
                          ("goal_without_use_case", "Goal-2")})

    def test_benefits_need_no_goal_until_goals_are_extracted(self):
        state = library_state()
        del state["goal_metadata"]
        graph = build_artifact_graph(state)
        self.assertNotIn("benefit_without_goal", {g["kind"] for g in graph["gaps"]})
        self.assertIn("No goal artifacts were extracted.", [g["detail"] for g in graph["gaps"]])

    def test_duplicate_id_keeps_first_artifact(self):
        state = library_state()
        state["stakeholder_metadata"]["stakeholders"].append(stakeholder(1, "Copy"))
        graph = build_artifact_graph(state)

        matches = [n for n in graph["nodes"] if n["id"] == "Stakeholder-1"]
        self.assertEqual([n["label"] for n in matches], ["Students"])
        self.assertIn(("duplicate_id", "Stakeholder-1"), gap_set(graph))
        self.assertEqual(len(graph["edges"]), len(edge_set(graph)))


class ArtifactGraphStepTests(unittest.TestCase):
    def test_step_stores_graph_and_keeps_earlier_state(self):
        step = build_artifact_graph_step(InMemorySaver())
        config = {"configurable": {"thread_id": self.id()}}
        state = library_state()

        result = step.invoke(state, config)

        self.assertEqual(result["artifact_graph"], build_artifact_graph(state))
        self.assertEqual(result["persona_metadata"], state["persona_metadata"])
        self.assertEqual(step.get_state(config).values["artifact_graph"],
                         result["artifact_graph"])

    def test_runs_after_real_user_modelling_steps(self):
        """PRD -> stakeholders -> personas -> artifact graph, with a fake model."""
        stakeholder_model, persona_model = Mock(), Mock()
        stakeholder_model.invoke.return_value = {"stakeholders": [
            {k: v for k, v in stakeholder(n, name).items() if k != "stakeholder_id"}
            for n, name in [(1, "Students"), (2, "Front-desk staff")]
        ]}
        persona_model.invoke.return_value = {"personas": [
            {k: v for k, v in persona(1, "Stakeholder-1", name="Priya").items()
             if k != "persona_id"},
            {k: v for k, v in persona(2, None, name="Morgan").items()
             if k != "persona_id"},
        ]}
        patches = [patch.object(stakeholder_node, "stakeholder_extractor", stakeholder_model),
                   patch.object(persona_node, "persona_extractor", persona_model)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        builder = StateGraph(AgentState)
        builder.add_node("user_modelling", build_user_modelling())
        builder.add_node("artifact_graph", build_artifact_graph_step())
        builder.add_edge(START, "user_modelling")
        builder.add_edge("user_modelling", "artifact_graph")
        builder.add_edge("artifact_graph", END)
        pipeline = builder.compile(checkpointer=InMemorySaver())

        state = library_state()
        del state["stakeholder_metadata"], state["persona_metadata"]
        result = pipeline.invoke(state, {"configurable": {"thread_id": self.id()}})
        graph = result["artifact_graph"]

        self.assertIn(("Persona-1", "represents", "Stakeholder-1"), edge_set(graph))
        self.assertIn(("Stakeholder-2", "concerned_with", "Intent-1"), edge_set(graph))
        self.assertEqual(
            {g for g in gap_set(graph) if g[0] != "unaddressed_problem"},
            {("unlinked_persona", "Persona-2"),
             ("stakeholder_without_persona", "Stakeholder-2")},
        )


if __name__ == "__main__":
    unittest.main()
