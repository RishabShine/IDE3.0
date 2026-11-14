import unittest
from collections import deque
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agentic_flow.user_modelling.graph import build_user_modelling
from agentic_flow.user_modelling.stakeholders import node, prompt
from agentic_flow.user_modelling.stakeholders.schema import (
    IndividualStakeHolderEvaluation,
    StakeHolderDraftUpdate,
    StakeHolderEvaluation,
    StakeHolderResponse,
    StakeHolderSuggestionDecision,
    SuggestedStakeHolder,
)


class StubModel:
    """Supply model responses while exercising real graph/checkpoint behaviour."""

    def __init__(self):
        self.responses = deque()
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("Unexpected model call")
        return self.responses.popleft()


def draft(stakeholder_id=None, **changes):
    data = dict(
        stakeholder_id=stakeholder_id,
        name="Front-desk library staff",
        involvement="direct",
        summary="Handle study-room bookings.",
        justification="Know current booking rules and exceptions.",
    )
    return StakeHolderDraftUpdate(**{**data, **changes})


def response(updates=(), decisions=(), feedback="", removed=()):
    return StakeHolderResponse(
        updates=list(updates),
        removed_stakeholder_ids=list(removed),
        suggestion_decisions=list(decisions),
        clarification_feedback=feedback,
    )


def evaluation(ids=(1,), suggestions=(), detail="met", overall="met"):
    return StakeHolderEvaluation(
        provided_stakeholders=[
            IndividualStakeHolderEvaluation(
                stakeholder_id=i,
                detail_verdict=detail,
                detail_feedback="Which staff roles do you mean?" if detail != "met" else "",
                relevance_verdict="met" if detail == "met" else "not_evaluated",
                relevance_feedback="",
                overlap_verdict="met" if detail == "met" else "not_evaluated",
                overlap_feedback="",
                overlap_stakeholder_ids=[],
                overall_verdict=overall,
            ) for i in ids
        ],
        suggested_stakeholders=list(suggestions),
    )


class StakeHolderFlowTests(unittest.TestCase):
    def setUp(self):
        self.processor = StubModel()
        self.evaluator = StubModel()
        for name, model in (
            ("stakeholder_response_processor", self.processor),
            ("stakeholder_evaluator", self.evaluator),
        ):
            patcher = patch.object(node, name, model)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.checkpointer = InMemorySaver()
        self.graph = build_user_modelling(self.checkpointer)
        self.config = {"configurable": {"thread_id": self.id()}}
        self.context = {
            "statement": "Self-service library room booking",
            "goals": ["Reduce staff booking workload"],
            "scope_exclusions": ["Equipment loans"],
            "constraints": ["Use university authentication"],
        }
        self.suggestion = SuggestedStakeHolder(
            name="University IT services",
            summary="Maintain university authentication.",
            justification="The application uses university authentication.",
        )

    def start(self):
        return self.graph.invoke({"captured_intent": self.context}, self.config)

    def resume(self, text):
        return self.graph.invoke(Command(resume=text), self.config)

    def message(self, result):
        return result["__interrupt__"][0].value["prompt_to_user"]

    def test_initialization_pauses_without_a_model_call(self):
        result = self.start()
        self.assertEqual(self.message(result), prompt.STAKEHOLDER_STARTER_PROMPT)
        self.assertFalse(self.processor.calls)
        self.assertFalse(self.evaluator.calls)
        metadata = self.graph.get_state(self.config).values["stakeholder_metadata"]
        self.assertEqual(metadata["intent_context"], self.context)
        self.assertIn("Equipment loans", metadata["messages"][1].content)

    def test_declined_suggestion_is_not_repeated_and_approval_is_explicit(self):
        self.processor.responses.extend([
            response([draft()]),
            response(decisions=[StakeHolderSuggestionDecision(
                name=self.suggestion.name, decision="decline", reason="Covered elsewhere."
            )]),
        ])
        # A repeated model suggestion must not undo the user's rejection.
        self.evaluator.responses.extend([
            evaluation(suggestions=[self.suggestion]),
            evaluation(suggestions=[self.suggestion]),
        ])
        self.start()
        result = self.resume("Front-desk staff handle bookings and know the rules.")
        self.assertIn("Suggested stakeholder: University IT services", self.message(result))
        result = self.resume("Leave out University IT services; covered elsewhere.")
        self.assertIn("Enter APPROVE", self.message(result))
        self.assertFalse(result["stakeholder_metadata"]["user_confirmed"])
        result = self.resume("APPROVE")
        metadata = result["stakeholder_metadata"]
        self.assertTrue(metadata["user_confirmed"])
        self.assertEqual(len(metadata["finalized_stakeholders"]), 1)
        self.assertEqual(metadata["pending_suggestions"], [])
        self.assertEqual(metadata["declined_suggestions"][0]["reason"], "Covered elsewhere.")
        self.assertEqual(len(self.evaluator.calls), 2)

    def test_history_survives_rebuilding_with_the_same_checkpointer(self):
        self.processor.responses.extend([
            response([draft(summary="", justification="")]),
            response([draft(1)]),
        ])
        self.evaluator.responses.extend([evaluation(detail="not_met"), evaluation()])
        self.start()
        result = self.resume("Library staff")
        self.assertIn("More detail needed", self.message(result))
        self.graph = build_user_modelling(self.checkpointer)
        result = self.resume("They handle bookings and explain booking exceptions.")
        metadata = result["stakeholder_metadata"]
        self.assertEqual(metadata["drafts"][0]["stakeholder_id"], 1)
        self.assertEqual(sum(isinstance(m, SystemMessage) for m in metadata["messages"]), 1)
        self.assertIn("Library staff", [m.content for m in metadata["messages"]])
        self.assertIn("Enter APPROVE", self.message(result))
        self.assertIn("Equipment loans", self.evaluator.calls[-1][1].content)

    def test_edits_at_confirmation_require_evaluation_and_new_confirmation(self):
        self.processor.responses.extend([
            response([draft()]),
            response([draft(1, summary="Handle bookings and cancellations.")]),
        ])
        self.evaluator.responses.extend([evaluation(), evaluation()])
        self.start()
        self.resume("Front-desk staff handle bookings and know the rules.")
        result = self.resume("Add that front-desk staff also handle cancellations.")
        metadata = result["stakeholder_metadata"]
        self.assertFalse(metadata["user_confirmed"])
        self.assertEqual(metadata["draft_version"], 2)
        self.assertIn("cancellations", self.message(result))
        result = self.resume("APPROVE")
        self.assertEqual(result["stakeholder_metadata"]["approved_version"], 2)

    def test_unanswered_suggestions_remain_pending(self):
        self.processor.responses.extend([response([draft()]), response()])
        self.evaluator.responses.extend([
            evaluation(suggestions=[self.suggestion]), evaluation(),
        ])
        self.start()
        self.resume("Front-desk staff handle bookings.")
        result = self.resume("The existing staff description is fine.")
        self.assertIn("Suggested stakeholder: University IT services", self.message(result))
        self.assertNotIn("Enter APPROVE", self.message(result))

    def test_accepted_suggestion_gets_a_new_id_and_requires_missing_detail(self):
        self.processor.responses.extend([
            response([draft()]),
            response(decisions=[StakeHolderSuggestionDecision(
                name=self.suggestion.name, decision="accept", reason=""
            )]),
        ])
        # Even if the model incorrectly passes it, classification is unknown.
        self.evaluator.responses.extend([
            evaluation(suggestions=[self.suggestion]), evaluation(ids=(1, 2)),
        ])
        self.start()
        self.resume("Front-desk staff handle bookings.")
        result = self.resume("Include University IT services.")
        metadata = result["stakeholder_metadata"]
        self.assertEqual([d["stakeholder_id"] for d in metadata["drafts"]], [1, 2])
        self.assertEqual(metadata["pending_suggestions"], [])
        self.assertIn("More detail needed", self.message(result))
        self.assertIn("involvement", self.message(result))

    def test_empty_list_and_early_approve_do_not_finalize(self):
        self.processor.responses.append(response())
        self.evaluator.responses.append(evaluation(ids=()))
        self.start()
        result = self.resume("APPROVE")
        self.assertIn("Please provide at least one stakeholder", self.message(result))
        self.assertEqual(result["stakeholder_metadata"]["finalized_stakeholders"], [])

    def test_removed_group_is_not_immediately_suggested_again(self):
        self.processor.responses.extend([
            response([draft(), draft(name=self.suggestion.name, involvement="indirect")]),
            response(removed=[2]),
        ])
        self.evaluator.responses.extend([
            evaluation(ids=(1, 2)), evaluation(suggestions=[self.suggestion]),
        ])
        self.start()
        self.resume("Include front-desk staff and university IT services.")
        result = self.resume("Remove stakeholder 2.")
        metadata = result["stakeholder_metadata"]
        self.assertEqual([d["stakeholder_id"] for d in metadata["drafts"]], [1])
        self.assertEqual(metadata["next_draft_id"], 3)
        self.assertEqual(metadata["pending_suggestions"], [])
        self.assertIn("Enter APPROVE", self.message(result))

    def test_evaluator_cannot_skip_current_drafts(self):
        self.processor.responses.append(response([draft()]))
        self.evaluator.responses.append(evaluation(ids=()))
        self.start()
        with self.assertRaisesRegex(ValueError, "each current draft exactly once"):
            self.resume("Front-desk staff handle bookings.")
        metadata = self.graph.get_state(self.config).values["stakeholder_metadata"]
        self.assertIsNone(metadata["evaluation"])
        self.assertFalse(metadata["user_confirmed"])

    def test_parent_graph_runs_sson_then_stakeholders_and_ends(self):
        from agentic_flow.capture_intent import node as capture_node
        from agentic_flow.capture_intent.schema import IntentSSONEvaluation
        from agentic_flow.graph import build_ide3_chat

        sson_evaluator = StubModel()
        sson_evaluator.responses.append(IntentSSONEvaluation(
            evaluation_of_statement="met",
            evaluation_of_statement_feedback="The need is clear.",
        ))
        self.processor.responses.append(response([draft()]))
        self.evaluator.responses.append(evaluation())
        self.graph = build_ide3_chat(self.checkpointer)

        with patch.object(capture_node, "base_model", SimpleNamespace(
            with_structured_output=lambda schema: sson_evaluator
        )):
            result = self.start()
            self.assertIn("Single Statement of Need", self.message(result))
            result = self.resume("Students book rooms without staff help.")
            self.assertEqual(self.message(result), prompt.STAKEHOLDER_STARTER_PROMPT)
            result = self.resume("Front-desk staff handle bookings and know the rules.")
            self.assertIn("Enter APPROVE", self.message(result))
            result = self.resume("APPROVE")

        self.assertNotIn("__interrupt__", result)
        self.assertEqual(result["intent_metadata"]["evaluation_of_statement"], "met")
        self.assertTrue(result["stakeholder_metadata"]["user_confirmed"])
        self.assertEqual(result["stakeholder_metadata"]["intent_context"], self.context)
        self.assertEqual(self.graph.get_state(self.config).next, ())

    def test_parent_checkpoint_resumes_a_retry_inside_sson(self):
        from agentic_flow.capture_intent import node as capture_node
        from agentic_flow.capture_intent.schema import IntentSSONEvaluation
        from agentic_flow.graph import build_ide3_chat

        sson_evaluator = StubModel()
        sson_evaluator.responses.extend([
            IntentSSONEvaluation(
                evaluation_of_statement="not_met",
                evaluation_of_statement_feedback="Who needs the booking capability?",
            ),
            IntentSSONEvaluation(
                evaluation_of_statement="met",
                evaluation_of_statement_feedback="The need is clear.",
            ),
        ])
        self.processor.responses.append(response([draft()]))
        self.evaluator.responses.append(evaluation())
        self.graph = build_ide3_chat(self.checkpointer)
        with patch.object(capture_node, "base_model", SimpleNamespace(
            with_structured_output=lambda schema: sson_evaluator
        )):
            self.start()
            result = self.resume("A booking app.")
            self.assertIn("Who needs", self.message(result))
            result = self.resume("Students book rooms without staff help.")
            self.assertEqual(self.message(result), prompt.STAKEHOLDER_STARTER_PROMPT)
            self.resume("Front-desk staff handle bookings and know the rules.")
            result = self.resume("APPROVE")
        self.assertEqual(result["intent_metadata"]["attempt_number"], 2)
        self.assertEqual(len(result["stakeholder_metadata"]["finalized_stakeholders"]), 1)


if __name__ == "__main__":
    unittest.main()
