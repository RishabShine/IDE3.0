import re
import unittest
from collections import deque
from unittest.mock import patch

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agentic_flow.goal2story import node, prompt
from agentic_flow.goal2story.artifacts import collect_stories
from agentic_flow.goal2story.graph import build_goal2story
from agentic_flow.goal2story.schema import (
    GeneratedStory,
    InvestCheck,
    StoryList,
    StoryRevision,
    StoryUpdate,
)
from agentic_flow.state import RED_FLAG


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


def goal_of(messages) -> str:
    task = next(m.content for m in reversed(messages) if "Write the user stories" in m.content)
    return re.search(r"for (Goal-\d+)", task).group(1)


def stories_for(messages):
    goal_id = goal_of(messages)
    return StoryList(stories=[
        GeneratedStory(actor="Students", action=f"book a room for {goal_id}",
                       expected_outcome="my group has a place to study"),
        GeneratedStory(actor="Front-desk staff", action=f"see bookings for {goal_id}",
                       expected_outcome="I stop answering emails"),
        GeneratedStory(actor="Students", action=f"cancel a booking for {goal_id}",
                       expected_outcome="others can use the room"),
        GeneratedStory(actor="Students", action=f"extra story for {goal_id}",
                       expected_outcome="this one is over the cap"),
    ])


def passes(messages):
    return InvestCheck(failed_criteria=[], feedback="", open_questions=[])


def no_changes(**fields):
    return {"updates": [], "removed_ids": [], "clarification_feedback": "", **fields}


STAKEHOLDERS = [
    {"stakeholder_id": "Stakeholder-1", "name": "Students", "involvement": "direct",
     "summary": "Book rooms.", "justification": "Main users."},
    {"stakeholder_id": "Stakeholder-2", "name": "Front-desk staff", "involvement": "direct",
     "summary": "Handle bookings today.", "justification": "Know the rules."},
]


def goal(goal_id, statement, actors, **changes):
    return {"goal_id": goal_id, "statement": statement, "source": None, "benefit_ids": [],
            "actors": actors, "goal_type": "hard", "resources": [], "plans": "",
            "justification": "", **changes}


def actor(name, stakeholder_id):
    return {"name": name, "stakeholder_id": stakeholder_id, "role": "", "involvement": ""}


GOALS = [
    goal("Goal-1", f"{RED_FLAG} Cut staff time on bookings to under 1 h/week",
         [actor("Students", "Stakeholder-1"), actor("Front-desk staff", "Stakeholder-2")],
         benefit_ids=["Benefit-1"], plans="Students book rooms themselves.",
         resources=["room calendar"]),
    goal("Goal-2", "Never double book a room", [actor("Students", "Stakeholder-1")]),
]


class Goal2StoryTestCase(unittest.TestCase):
    def setUp(self):
        self.stubs = {
            StoryList: StubModel(stories_for),
            InvestCheck: StubModel(passes),
            StoryRevision: StubModel(),
        }
        patcher = patch.object(node, "_model", lambda schema: self.stubs[schema])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.checkpointer = InMemorySaver()
        self.graph = build_goal2story(self.checkpointer)
        self.config = {"configurable": {"thread_id": self.id()}}
        self.state = {
            "captured_intent": {
                "single_statement_intent": f"{RED_FLAG} Let students book rooms without staff.",
                "benefits": [{"id": "Benefit-1", "description": "Under 1 hour a week on emails.",
                              "addresses": [], "measure": "under 1 hour", "kind": "hard",
                              "source": None}],
            },
            "stakeholder_metadata": {"instructions": "", "stakeholders": STAKEHOLDERS},
            "goal_metadata": {"instructions": "", "goals": GOALS},
        }

    def start(self, **changes):
        return self.graph.invoke({**self.state, **changes}, self.config)

    def resume(self, text):
        return self.graph.invoke(Command(resume=text), self.config)

    def message(self, result):
        return result["__interrupt__"][0].value["prompt_to_user"]

    def meta(self):
        return self.graph.get_state(self.config).values["goal2story_metadata"]

    def ids(self):
        return [s["id"] for s in self.meta()["stories"]]


class Goal2StoryFlowTests(Goal2StoryTestCase):
    def test_takes_every_extracted_goal_and_generates_nothing_else(self):
        result = self.start()
        meta = self.meta()
        self.assertEqual([g["id"] for g in meta["goals"]], ["Goal-1", "Goal-2"])
        first = meta["goals"][0]
        self.assertEqual(first["statement"], "Cut staff time on bookings to under 1 h/week")
        self.assertEqual(first["delivers_benefits"], [
            {"id": "Benefit-1", "description": "Under 1 hour a week on emails.",
             "measure": "under 1 hour"}])
        self.assertEqual(meta["context"]["stakeholders"], STAKEHOLDERS)
        self.assertEqual(meta["context"]["statement_of_need"],
                         "Let students book rooms without staff.")
        # only stories and their INVEST checks call the model
        self.assertEqual(set(self.stubs), {StoryList, InvestCheck, StoryRevision})
        self.assertEqual(len(self.stubs[StoryList].calls), 2)
        self.assertIn("review the user stories", self.message(result))

    def test_one_story_call_per_goal_and_each_story_traces_to_its_goal(self):
        self.start()
        stories = self.meta()["stories"]
        self.assertEqual(self.ids(), ["US-1", "US-2", "US-3", "US-4", "US-5", "US-6"])
        self.assertEqual([s["parent_id"] for s in stories], ["Goal-1"] * 3 + ["Goal-2"] * 3)
        self.assertEqual(stories[0]["text"],
                         "As Students, I want to book a room for Goal-1, so that my group "
                         "has a place to study.")
        # the actor's stakeholder comes from the goal's own actor list
        self.assertEqual([s["stakeholder_id"] for s in stories],
                         ["Stakeholder-1", "Stakeholder-2", "Stakeholder-1",
                          "Stakeholder-1", None, "Stakeholder-1"])
        request = self.stubs[StoryList].calls[0][1].content
        self.assertIn('"plans": "Students book rooms themselves."', request)
        self.assertIn('"room calendar"', request)
        self.assertIn("Write the user stories for Goal-1, at most 3", request)

    def test_stories_per_goal_is_configurable(self):
        self.start(goal2story_metadata={"stories_per_goal": 1})
        self.assertEqual(self.ids(), ["US-1", "US-2"])

    def test_no_goals_skips_goal2story_without_a_model_call(self):
        for state in ({"goal_metadata": {"instructions": "", "goals": []}},
                      {"goal_metadata": None}):
            with self.subTest(state=state):
                self.config = {"configurable": {"thread_id": f"{self.id()}-{len(state)}{state}"}}
                result = self.start(**state)
                self.assertNotIn("__interrupt__", result)
                meta = result["goal2story_metadata"]
                self.assertTrue(meta["skipped"])
                self.assertEqual(meta["stories"], [])
        self.assertFalse(any(stub.calls for stub in self.stubs.values()))

    def test_revision_edits_removes_and_adds_with_new_ids(self):
        self.stubs[StoryRevision].responses.append(StoryRevision(**no_changes(
            updates=[
                StoryUpdate(id="US-1", parent_id="Goal-1", actor="Students",
                            action="reserve a room", expected_outcome="we can study"),
                StoryUpdate(id=None, parent_id="Goal-2", actor="Front-desk staff",
                            action="see clashes", expected_outcome="no room is booked twice"),
            ],
            removed_ids=["US-3"],
        )))
        self.start()
        result = self.resume("US-1: reserving; remove US-3; add a staff story for Goal-2")
        self.assertEqual(self.ids(), ["US-1", "US-2", "US-4", "US-5", "US-6", "US-7"])
        story = self.meta()["stories"][-1]
        self.assertEqual((story["parent_id"], story["stakeholder_id"]), ("Goal-2", None))
        self.assertIn("US-1** As Students, I want to reserve a room", self.message(result))
        self.assertEqual(self.meta()["edit_log"][0]["removed"], ["US-3"])

    def test_invalid_revision_operations_are_skipped_and_reported(self):
        self.stubs[StoryRevision].responses.append(StoryRevision(**no_changes(
            updates=[
                StoryUpdate(id=None, parent_id="Goal-9", actor="A", action="b",
                            expected_outcome="c"),
                StoryUpdate(id="US-99", parent_id="Goal-1", actor="A", action="b",
                            expected_outcome="c"),
                StoryUpdate(id="US-1", parent_id="Goal-1", actor=" ", action="b",
                            expected_outcome="c"),
            ],
            removed_ids=["US-42"],
        )))
        self.start()
        message = self.message(self.resume("do things"))
        for note in ("no such goal", "Could not change US-99", "a field was empty",
                     "Could not remove US-42"):
            self.assertIn(note, message)
        self.assertEqual(len(self.ids()), 6)

    def test_unclear_request_shows_the_models_question(self):
        self.stubs[StoryRevision].responses.append(StoryRevision(**no_changes(
            clarification_feedback="Which story should change?")))
        self.start()
        self.assertIn("Which story should change?", self.message(self.resume("fix it")))

    def test_approve_with_no_stories_asks_for_one(self):
        self.stubs[StoryList].default = lambda m: StoryList(stories=[])
        self.start()
        result = self.resume("APPROVE")
        self.assertIn(prompt.EMPTY_STORIES_FEEDBACK, self.message(result))

    def test_format_doctor_repairs_invalid_json_once(self):
        self.stubs[StoryList].responses.append(ValueError("Invalid JSON: unquoted key"))
        self.start()
        calls = self.stubs[StoryList].calls
        self.assertEqual(len(calls), 3)  # Goal-1 twice (repair), Goal-2 once
        self.assertIn("could not be read as valid JSON", calls[1][-1].content)
        self.assertIn("unquoted key", calls[1][-1].content)

    def test_format_doctor_gives_up_after_one_repair(self):
        self.stubs[StoryList].responses.extend([ValueError("bad"), ValueError("still bad")])
        with self.assertRaisesRegex(ValueError, "still bad"):
            self.start()

    def test_invest_warnings_are_shown_and_open_questions_are_handed_off(self):
        self.stubs[InvestCheck].responses.append(InvestCheck(
            failed_criteria=["testable", "small"],
            feedback="No booking rules yet.",
            open_questions=["How long can a booking be?", " "],
        ))
        self.stubs[StoryRevision].responses.append(StoryRevision(**no_changes(
            updates=[StoryUpdate(id="US-2", parent_id="Goal-1", actor="Students",
                                 action="reserve a room", expected_outcome="we can study")]
        )))
        message = self.message(self.start())
        self.assertIn("⚠ INVEST: small, testable. No booking rules yet.", message)
        self.assertIn("? How long can a booking be?", message)
        request = self.stubs[InvestCheck].calls[0][1].content
        self.assertIn('"id": "Goal-1"', request)

        # only the changed story is checked again
        self.resume("US-2: make it about reserving a room")
        self.assertEqual(len(self.stubs[InvestCheck].calls), 7)
        result = self.resume("APPROVE")
        meta = result["goal2story_metadata"]
        self.assertEqual(meta["open_questions"], [
            {"id": "Q-1", "story_id": "US-1", "question": "How long can a booking be?"}
        ])
        first = meta["finalized_stories"][0]
        self.assertEqual(first["goal"], "Cut staff time on bookings to under 1 h/week")
        self.assertEqual(first["trace"], ["Goal-1", "Benefit-1"])

    def test_history_survives_rebuilding_with_the_same_checkpointer(self):
        self.start()
        self.graph = build_goal2story(self.checkpointer)
        result = self.resume("APPROVE")
        self.assertNotIn("__interrupt__", result)
        self.assertEqual(len(result["goal2story_metadata"]["finalized_stories"]), 6)
        self.assertEqual(len(self.stubs[StoryList].calls), 2)

    def test_runs_on_the_goals_stage_output(self):
        """Goal2Story is outside the main flow; it runs after the goals stage."""
        from agentic_flow.goals import node as goal_node
        from agentic_flow.goals.graph import build_goals

        goal_extractor = StubModel(default=lambda messages: {"goals": [{
            "statement": "Cut staff time", "goal_type": "hard", "resources": [],
            "plans": "", "justification": "", "benefit_ids": ["Benefit-1"],
            "actors": [{"name": "Students", "stakeholder_id": "Stakeholder-1",
                        "role": "", "involvement": ""}],
        }]})
        state = {**self.state, "prd": "Students email the front desk to book rooms."}
        del state["goal_metadata"]
        with patch.object(goal_node, "goal_extractor", goal_extractor):
            state = build_goals().invoke(state)
        result = self.graph.invoke(state, self.config)
        meta = result["goal2story_metadata"]
        self.assertEqual([g["id"] for g in meta["goals"]], ["Goal-1"])
        self.assertEqual(meta["goals"][0]["statement"], "Cut staff time")
        self.assertEqual(len(meta["finalized_stories"]), 3)
        self.assertEqual(meta["finalized_stories"][0]["trace"], ["Goal-1", "Benefit-1"])


class Goal2StoryPrdModeTests(Goal2StoryTestCase):
    """PRD mode: stories are written for every goal and accepted without a stop."""

    def setUp(self):
        super().setUp()
        self.state["prd"] = "Students email the front desk to book rooms."

    def test_prd_runs_straight_through(self):
        result = self.start()
        self.assertNotIn("__interrupt__", result)
        meta = result["goal2story_metadata"]
        self.assertTrue(meta["approved"])
        self.assertEqual(len(meta["finalized_stories"]), 6)
        self.assertIn("Students email", meta["context"]["prd"])

    def test_auto_can_be_turned_off_with_a_prd(self):
        result = self.start(goal2story_metadata={"auto": False})
        self.assertIn("review the user stories", self.message(result))

    def test_collector_links_every_story_to_its_goal_and_stakeholder(self):
        result = self.start()
        nodes, edges = collect_stories(result)
        self.assertEqual([n["type"] for n in nodes], ["story"] * 6)
        self.assertIn({"source": "US-2", "target": "Goal-1", "relation": "implements"}, edges)
        self.assertIn({"source": "US-2", "target": "Stakeholder-2",
                       "relation": "performed_by"}, edges)
        # US-5's actor is not one of Goal-2's actors, so it has no stakeholder link
        self.assertFalse(any(e["source"] == "US-5" and e["relation"] == "performed_by"
                             for e in edges))

    def test_collector_is_empty_before_goal2story_runs(self):
        self.assertEqual(collect_stories(self.state), ([], []))


if __name__ == "__main__":
    unittest.main()
