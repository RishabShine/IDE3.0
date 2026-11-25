import unittest
from collections import deque
from unittest.mock import patch

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agentic_flow.goal2story import node, prompt
from agentic_flow.goal2story.graph import build_goal2story
from agentic_flow.goal2story.schema import (
    ActorList,
    ActorRevision,
    ActorUpdate,
    DeliverableList,
    DeliverableRevision,
    ExtractedGoal,
    GeneratedActor,
    GeneratedDeliverable,
    GeneratedImpact,
    GeneratedStory,
    ImpactList,
    ImpactRevision,
    ImpactUpdate,
    InvestCheck,
    StoryRevision,
    StoryUpdate,
)


class StubModel:
    """Queued responses first, then `default(messages)`. Exceptions are raised."""

    def __init__(self, default=None):
        self.responses = deque()
        self.default = default
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        if self.responses:
            response = self.responses.popleft()
        elif self.default is not None:
            response = self.default(messages)
        else:
            raise AssertionError("Unexpected model call")
        if isinstance(response, Exception):
            raise response
        return response


def task(messages) -> str:
    return messages[-1].content


def actors(*names):
    return ActorList(actors=[
        GeneratedActor(name=n, description=f"{n} affect bookings.", stakeholder=s)
        for n, s in names
    ])


def impacts_for(messages):
    parent = task(messages).rsplit(" ", 1)[1].rstrip(".")
    return ImpactList(impacts=[
        GeneratedImpact(description=f"impact {k} of {parent}") for k in (1, 2, 3)
    ])


def deliverables_for(messages):
    parent = task(messages).rsplit(" ", 1)[1].rstrip(".")
    return DeliverableList(deliverables=[
        GeneratedDeliverable(description=f"deliverable {k} of {parent}") for k in (1, 2)
    ])


def story_for(messages):
    parent = task(messages).rsplit(" ", 1)[1].rstrip(".")
    return GeneratedStory(
        actor="Student", action=f"use {parent}", expected_outcome="my group has a room"
    )


def passes(messages):
    return InvestCheck(failed_criteria=[], feedback="", open_questions=[])


def no_changes(**fields):
    return {"updates": [], "removed_ids": [], "clarification_feedback": "", **fields}


STAKEHOLDERS = [
    {"stakeholder_id": 1, "name": "Students", "involvement": "direct",
     "summary": "Book rooms.", "justification": "Main users."},
    {"stakeholder_id": 2, "name": "Front-desk staff", "involvement": "direct",
     "summary": "Handle bookings today.", "justification": "Know the rules."},
]


class Goal2StoryTestCase(unittest.TestCase):
    def setUp(self):
        self.stubs = {
            ExtractedGoal: StubModel(),
            ActorList: StubModel(),
            ImpactList: StubModel(impacts_for),
            DeliverableList: StubModel(deliverables_for),
            GeneratedStory: StubModel(story_for),
            InvestCheck: StubModel(passes),
            ActorRevision: StubModel(),
            ImpactRevision: StubModel(),
            DeliverableRevision: StubModel(),
            StoryRevision: StubModel(),
        }
        self.stubs[ActorList].default = lambda m: actors(
            ("Students", "Students"), ("Front-desk staff", "Front-desk staff"), ("Extra", "Students")
        )
        patcher = patch.object(node, "_model", lambda schema: self.stubs[schema])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.checkpointer = InMemorySaver()
        self.graph = build_goal2story(self.checkpointer)
        self.config = {"configurable": {"thread_id": self.id()}}
        self.state = {
            "project_context": "Mills Library has 20 study rooms.",
            "intent_metadata": {"single_statement_intent": "Let students book rooms without staff."},
            "captured_intent": {"goals": ["Cut staff time on bookings to under 1 h/week"]},
            "stakeholder_metadata": {"instructions": "", "stakeholders": STAKEHOLDERS},
        }

    def start(self, **changes):
        return self.graph.invoke({**self.state, **changes}, self.config)

    def resume(self, text):
        return self.graph.invoke(Command(resume=text), self.config)

    def message(self, result):
        return result["__interrupt__"][0].value["prompt_to_user"]

    def meta(self):
        return self.graph.get_state(self.config).values["goal2story_metadata"]

    def ids(self, level):
        return [i["id"] for i in self.meta()[level]]

    def approve_all(self):
        result = None
        for _ in node.LEVELS:
            result = self.resume("APPROVE")
        return result


class Goal2StoryFlowTests(Goal2StoryTestCase):
    def test_goal_is_proposed_from_context_without_a_model_call(self):
        result = self.start()
        self.assertIn("Proposed goal: Cut staff time", self.message(result))
        self.assertFalse(any(stub.calls for stub in self.stubs.values()))
        context = self.meta()["context"]
        self.assertEqual(context["confirmed_stakeholders"], STAKEHOLDERS)
        self.assertIn("Let students book", context["statement_of_need"])

    def test_typed_goal_replaces_the_proposal_and_empty_reply_asks_again(self):
        self.start(captured_intent=None)
        result = self.resume("APPROVE")  # nothing proposed, so nothing to approve
        self.assertIn(prompt.GOAL_EMPTY_FEEDBACK, self.message(result))
        result = self.resume("  Halve   double bookings  ")
        self.assertEqual(self.meta()["goal"], "Halve double bookings")
        self.assertIn("review the actors", self.message(result))

    def test_full_run_builds_the_impact_map_with_stable_ids_and_traces(self):
        self.start()
        result = self.resume("APPROVE")
        # n = 2 caps the model's three actors and three impacts per actor
        self.assertEqual(self.ids("actors"), ["A-1", "A-2"])
        self.assertIn("A-2 Front-desk staff", self.message(result))
        result = self.resume("APPROVE")
        self.assertEqual(self.ids("impacts"), ["I-1.1", "I-1.2", "I-2.1", "I-2.2"])
        self.assertIn("Under A-1 (Students):", self.message(result))
        result = self.resume("APPROVE")
        self.assertEqual(len(self.ids("deliverables")), 8)
        self.assertIn("D-1.1.2", self.ids("deliverables"))
        self.assertIn("Under I-2.1 (Front-desk staff → impact 1 of A-2):", self.message(result))
        result = self.resume("APPROVE")
        self.assertEqual(self.ids("stories"), [f"US-{k}" for k in range(1, 9)])
        self.assertIn("As a Student, I want to use D-1.1.2, so that my group has a room.",
                      self.message(result))
        result = self.resume("APPROVE")

        self.assertNotIn("__interrupt__", result)
        meta = result["goal2story_metadata"]
        story = next(s for s in meta["finalized_stories"] if s["id"] == "US-2")
        self.assertEqual(story["trace"], ["A-1", "I-1.1", "D-1.1.2"])
        self.assertEqual(story["goal"], "Cut staff time on bookings to under 1 h/week")
        self.assertEqual(meta["approved_levels"], list(node.LEVELS))
        self.assertEqual(len(self.stubs[InvestCheck].calls), 8)
        # each agent sees the anchors and its own branch (Ref Info)
        impact_call = task(self.stubs[ImpactList].calls[0])
        self.assertIn("Mills Library has 20 study rooms", impact_call)
        self.assertIn('"id": "A-1"', impact_call)
        story_call = task(self.stubs[GeneratedStory].calls[1])
        for item_id in ("A-1", "I-1.1", "D-1.1.2"):
            self.assertIn(f'"id": "{item_id}"', story_call)

    def test_n_per_parent_is_configurable(self):
        self.start(goal2story_metadata={"n_per_parent": 3})
        self.resume("APPROVE")
        self.assertEqual(self.ids("actors"), ["A-1", "A-2", "A-3"])
        self.resume("APPROVE")
        self.assertEqual(len(self.ids("impacts")), 9)

    def test_revision_edits_removes_and_adds_with_new_ids(self):
        self.stubs[ImpactRevision].responses.append(ImpactRevision(**no_changes(
            updates=[
                ImpactUpdate(id="I-1.1", parent_id="A-1", description="books without staff"),
                ImpactUpdate(id=None, parent_id="A-2", description="stops answering emails"),
            ],
            removed_ids=["I-1.2"],
        )))
        self.start()
        self.resume("APPROVE")
        self.resume("APPROVE")
        result = self.resume("Reword I-1.1, drop I-1.2, and add one for staff about emails.")
        self.assertEqual(self.ids("impacts"), ["I-1.1", "I-2.1", "I-2.2", "I-2.3"])
        self.assertIn("I-1.1** books without staff", self.message(result))
        self.assertNotIn("I-1.2", self.message(result))
        log = self.meta()["edit_log"][-1]
        self.assertEqual((log["updated"], log["added"], log["removed"]),
                         (["I-1.1"], ["I-2.3"], ["I-1.2"]))
        self.resume("APPROVE")
        # deliverables are only generated for the impacts that were approved
        parents = {d["parent_id"] for d in self.meta()["deliverables"]}
        self.assertEqual(parents, {"I-1.1", "I-2.1", "I-2.2", "I-2.3"})

    def test_invalid_revision_operations_are_skipped_and_reported(self):
        self.stubs[ImpactRevision].responses.append(ImpactRevision(**no_changes(
            updates=[
                ImpactUpdate(id="I-9.9", parent_id="A-1", description="x"),
                ImpactUpdate(id=None, parent_id="A-7", description="y"),
            ],
            removed_ids=["I-5.5"],
        )))
        self.start()
        self.resume("APPROVE")
        self.resume("APPROVE")
        result = self.resume("Change some things.")
        message = self.message(result)
        for expected in ("Could not change I-9.9", "no such parent", "Could not remove I-5.5"):
            self.assertIn(expected, message)
        self.assertEqual(self.ids("impacts"), ["I-1.1", "I-1.2", "I-2.1", "I-2.2"])

    def test_unclear_request_shows_the_models_question(self):
        self.stubs[ActorRevision].responses.append(ActorRevision(**no_changes(
            clarification_feedback="Which actor should be renamed?"
        )))
        self.start()
        self.resume("APPROVE")
        result = self.resume("rename it")
        self.assertIn("Which actor should be renamed?", self.message(result))
        # the question is shown once, not on every later review
        self.stubs[ActorRevision].responses.append(ActorRevision(**no_changes(
            updates=[ActorUpdate(id="A-2", name="Library staff", description="d",
                                 stakeholder="Front-desk staff")]
        )))
        result = self.resume("Rename A-2 to Library staff")
        self.assertNotIn("Which actor", self.message(result))
        self.assertIn("A-2 Library staff", self.message(result))

    def test_approve_with_no_items_asks_for_one(self):
        self.stubs[ActorList].responses.append(ActorList(actors=[]))
        self.start()
        result = self.resume("APPROVE")
        self.assertIn("(none)", self.message(result))
        result = self.resume("APPROVE")
        self.assertIn("There are no actors yet", self.message(result))
        self.assertEqual(self.meta()["approved_levels"], [])

    def test_actor_outside_the_confirmed_stakeholders_is_flagged(self):
        self.stubs[ActorList].responses.append(actors(("Students", "Students"),
                                                      ("Janitors", "Cleaning staff")))
        self.start()
        result = self.resume("APPROVE")
        self.assertIn("Janitors", self.message(result))
        self.assertEqual(self.message(result).count(prompt.UNKNOWN_STAKEHOLDER_NOTE), 1)

    def test_stakeholder_id_from_the_model_is_mapped_to_its_name(self):
        self.stubs[ActorList].responses.append(actors(("Students", "1"), ("Staff", " 2 ")))
        self.start()
        result = self.resume("APPROVE")
        self.assertEqual([a["stakeholder"] for a in self.meta()["actors"]],
                         ["Students", "Front-desk staff"])
        self.assertNotIn(prompt.UNKNOWN_STAKEHOLDER_NOTE, self.message(result))

    def test_format_doctor_repairs_invalid_json_once(self):
        self.stubs[ActorList].responses.append(ValueError("Invalid JSON: unquoted key"))
        self.start()
        result = self.resume("APPROVE")
        calls = self.stubs[ActorList].calls
        self.assertEqual(len(calls), 2)
        self.assertIn("could not be read as valid JSON", calls[1][-1].content)
        self.assertIn("unquoted key", calls[1][-1].content)
        self.assertIn("A-1 Students", self.message(result))

    def test_format_doctor_gives_up_after_one_repair(self):
        self.stubs[ActorList].responses.extend([ValueError("bad"), ValueError("still bad")])
        self.start()
        with self.assertRaisesRegex(ValueError, "still bad"):
            self.resume("APPROVE")
        self.assertEqual(self.meta()["actors"], [])

    def test_invest_warnings_are_shown_and_open_questions_are_handed_off(self):
        self.stubs[InvestCheck].responses.append(InvestCheck(
            failed_criteria=["testable", "small"],
            feedback="No booking rules yet.",
            open_questions=["How long can a booking be?", " "],
        ))
        self.stubs[StoryRevision].responses.append(StoryRevision(**no_changes(
            updates=[StoryUpdate(id="US-2", parent_id="D-1.1.2", actor="Student",
                                 action="reserve a room", expected_outcome="we can study")]
        )))
        self.start()
        for _ in range(3):
            self.resume("APPROVE")
        result = self.resume("APPROVE")
        message = self.message(result)
        self.assertIn("⚠ INVEST: small, testable. No booking rules yet.", message)
        self.assertIn("? How long can a booking be?", message)

        # only the changed story is checked again
        result = self.resume("US-2: make it about reserving a room")
        self.assertEqual(len(self.stubs[InvestCheck].calls), 9)
        self.assertIn("US-2** As a Student, I want to reserve a room", self.message(result))
        result = self.resume("APPROVE")
        meta = result["goal2story_metadata"]
        self.assertEqual(meta["open_questions"], [
            {"id": "Q-1", "story_id": "US-1", "question": "How long can a booking be?"}
        ])

    def test_history_survives_rebuilding_with_the_same_checkpointer(self):
        self.start()
        self.resume("APPROVE")
        self.graph = build_goal2story(self.checkpointer)
        result = self.resume("APPROVE")
        self.assertIn("review the impacts", self.message(result))
        self.assertEqual(len(self.stubs[ActorList].calls), 1)

    def test_parent_graph_runs_user_modelling_then_goals_then_goal2story(self):
        from agentic_flow.capture_intent import node as capture_node
        from agentic_flow.goals import node as goal_node
        from agentic_flow.graph import build_ide3_chat
        from agentic_flow.user_modelling.stakeholders import node as stakeholder_node
        from agentic_flow.user_modelling.personas import node as persona_node
        from agentic_flow.user_modelling.stakeholders.schema import StakeHolderResponse

        intent_extractor = StubModel(default=lambda messages: {
            "intent": {
                "single_statement_intent": "Let students book rooms without staff.",
                "what": "book rooms without staff",
                "how": "self-service booking",
                "why": "staff spend too long on bookings",
                "problems": [],
                "benefits": [],
                "goals": ["Cut staff time"],
            }
        })
        extractor = StubModel()
        persona_extractor = StubModel(default=lambda messages: {"personas": []})
        goal_extractor = StubModel(default=lambda messages: {"goals": [{
            "statement": "Cut staff time", "actors": [], "goal_type": "hard",
            "resources": [], "plans": "", "justification": "",
        }]})
        extractor.responses.append(StakeHolderResponse(stakeholders=[{
            "name": "Front-desk library staff", "involvement": "direct",
            "summary": "Handle bookings and know the rules.",
            "justification": "Inform the booking workflow.",
        }]))
        self.stubs[ActorList].default = lambda m: actors(
            ("Front-desk staff", "Front-desk library staff")
        )
        self.graph = build_ide3_chat(self.checkpointer)

        with patch.object(capture_node, "intent_extractor", intent_extractor), \
                patch.object(stakeholder_node, "stakeholder_extractor", extractor), \
                patch.object(persona_node, "persona_extractor", persona_extractor), \
                patch.object(goal_node, "goal_extractor", goal_extractor):
            # Only human step for the PoC path: dump the PRD once.
            self.graph.invoke({}, self.config)
            result = self.resume(
                "Students book rooms without staff help.\n"
                "Front-desk staff handle bookings and know the rules."
            )

        self.assertNotIn("__interrupt__", result)
        meta = result["goal2story_metadata"]
        self.assertTrue(meta["auto"])
        self.assertEqual(meta["goal"], "Cut staff time")
        self.assertIn("Front-desk staff handle bookings", meta["context"]["prd"])
        self.assertEqual(meta["context"]["confirmed_stakeholders"][0]["name"],
                         "Front-desk library staff")
        self.assertEqual(
            result["captured_intent"]["single_statement_intent"],
            "Let students book rooms without staff.",
        )
        self.assertEqual(len(meta["finalized_stories"]), 4)
        self.assertEqual(len(intent_extractor.calls), 1)
        self.assertEqual(len(persona_extractor.calls), 1)
        self.assertEqual(len(goal_extractor.calls), 1)
        self.assertIn('"stakeholder_id": "Stakeholder-1"', goal_extractor.calls[0][1].content)
        self.assertEqual(result["goal_metadata"]["goals"][0]["goal_id"], "Goal-1")
        self.assertEqual(result["goal_metadata"]["goals"][0]["statement"], "Cut staff time")
        self.assertEqual(self.graph.get_state(self.config).next, ())



class Goal2StoryPrdModeTests(Goal2StoryTestCase):
    """PRD mode: the goal comes from the PRD and no level stops for review."""

    PRD = "Students email the front desk to book study rooms. Staff spend 6 h a week on it."

    def test_prd_runs_straight_through_using_the_proposed_goal(self):
        result = self.start(prd=self.PRD)
        self.assertNotIn("__interrupt__", result)
        meta = result["goal2story_metadata"]
        self.assertEqual(meta["goal"], "Cut staff time on bookings to under 1 h/week")
        self.assertEqual(meta["approved_levels"], list(node.LEVELS))
        self.assertEqual(len(meta["finalized_stories"]), 8)
        self.assertEqual(meta["context"]["prd"], self.PRD)
        self.assertFalse(self.stubs[ExtractedGoal].calls)

    def test_goal_is_extracted_from_the_prd_when_none_is_given(self):
        self.stubs[ExtractedGoal].responses.append(
            ExtractedGoal(goal="  Cut   booking emails  ")
        )
        personas = [{"persona_id": "Persona-1", "name": "Sam", "stakeholder_id": 1}]
        result = self.start(prd=self.PRD, captured_intent=None,
                            persona_metadata={"instructions": "", "personas": personas})
        meta = result["goal2story_metadata"]
        self.assertEqual(meta["goal"], "Cut booking emails")
        self.assertEqual(meta["context"]["personas"], personas)
        self.assertIn(self.PRD, self.stubs[ExtractedGoal].calls[0][-1].content)

    def test_empty_levels_do_not_stop_prd_mode(self):
        self.stubs[ActorList].default = lambda m: ActorList(actors=[])
        result = self.start(prd=self.PRD)
        self.assertNotIn("__interrupt__", result)
        self.assertEqual(result["goal2story_metadata"]["finalized_stories"], [])

    def test_auto_can_be_turned_off_with_a_prd(self):
        result = self.start(prd=self.PRD, goal2story_metadata={"auto": False})
        self.assertIn("Proposed goal:", result["__interrupt__"][0].value["prompt_to_user"])

    def test_collector_links_every_level_to_its_parent(self):
        from agentic_flow.goal2story.artifacts import GOAL_ID, collect_goal2story

        stakeholders = [{**s, "stakeholder_id": f"Stakeholder-{s['stakeholder_id']}"}
                        for s in STAKEHOLDERS]
        state = self.start(
            prd=self.PRD,
            stakeholder_metadata={"instructions": "", "stakeholders": stakeholders},
            captured_intent={"goals": ["Cut staff time"],
                             "single_statement_intent": "Let students book rooms."},
        )
        nodes, edges = collect_goal2story(state)
        types = [n["type"] for n in nodes]
        self.assertEqual([types.count(t) for t in
                          ("goal", "actor", "impact", "deliverable", "story")], [1, 2, 4, 8, 8])
        edge_set = {(e["source"], e["relation"], e["target"]) for e in edges}
        self.assertIn((GOAL_ID, "achieves", "Intent-1"), edge_set)
        self.assertIn(("A-1", "helps_reach", GOAL_ID), edge_set)
        self.assertIn(("A-1", "drawn_from", "Stakeholder-1"), edge_set)
        self.assertIn(("A-2", "drawn_from", "Stakeholder-2"), edge_set)
        self.assertIn(("I-1.1", "impact_of", "A-1"), edge_set)
        self.assertIn(("D-1.1.1", "supports", "I-1.1"), edge_set)
        self.assertIn(("US-1", "implements", "D-1.1.1"), edge_set)
        self.assertEqual(len(edges), 1 + 2 * 2 + 4 + 8 + 8)
        ids = {n["id"] for n in nodes}
        self.assertTrue(all(e["source"] in ids for e in edges))

    def test_collector_is_empty_before_a_goal_exists(self):
        from agentic_flow.goal2story.artifacts import collect_goal2story
        self.assertEqual(collect_goal2story({}), ([], []))


if __name__ == "__main__":
    unittest.main()
