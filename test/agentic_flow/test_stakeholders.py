import unittest
from collections import deque
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agentic_flow.user_modelling.stakeholders.graph import build_stakeholders
from agentic_flow.user_modelling.stakeholders import node, prompt
from agentic_flow.user_modelling.stakeholders.schema import (
    IndividualStakeHolderEvaluation,
    StakeHolderDraftUpdate,
    StakeHolderEvaluation,
    StakeHolderResponse,
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


def response(updates=(), feedback="", removed=()):
    return StakeHolderResponse(
        updates=list(updates),
        removed_stakeholder_ids=list(removed),
        clarification_feedback=feedback,
    )


def evaluation(ids=("Stakeholder-1",), detail="met", overall="met"):
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
        self.graph = build_stakeholders(self.checkpointer)
        self.config = {"configurable": {"thread_id": self.id()}}
        self.context = {
            "statement": "Self-service library room booking",
            "goals": ["Reduce staff booking workload"],
            "scope_exclusions": ["Equipment loans"],
            "constraints": ["Use university authentication"],
        }

    def start(self):
        return self.graph.invoke({"captured_intent": self.context}, self.config)

    def resume(self, text):
        return self.graph.invoke(Command(resume=text), self.config)

    def message(self, result):
        return result["__interrupt__"][0].value["prompt_to_user"]

    def test_starter_pauses_without_a_model_call_and_commits_on_resume(self):
        result = self.start()
        self.assertEqual(self.message(result), prompt.STAKEHOLDER_STARTER_PROMPT)
        self.assertFalse(self.processor.calls)
        self.assertFalse(self.evaluator.calls)
        # The combined node has not finished while waiting for the first reply.
        self.assertNotIn("stakeholder_metadata", self.graph.get_state(self.config).values)
        self.processor.responses.append(response([draft()]))
        self.evaluator.responses.append(evaluation())
        result = self.resume("Front-desk staff handle bookings.")
        metadata = result["stakeholder_metadata"]
        self.assertNotIn("intent_context", metadata)
        self.assertIn("Reduce staff booking workload", metadata["initial_context_message"])
        self.assertNotIn("previous_evaluation", metadata)
        self.assertIn("<asked_about>[]</asked_about>", self.processor.calls[0][-1].content)
        self.assertNotIn("<latest_evaluation>", self.processor.calls[0][-1].content)
        self.assertEqual(metadata["evaluated_draft_version"], metadata["draft_version"])
        self.assertEqual(metadata["last_prompt_to_user"], prompt.STAKEHOLDER_STARTER_PROMPT)
        self.assertNotIn("messages", metadata)

    def test_passing_drafts_require_explicit_approval(self):
        self.processor.responses.append(response([draft()]))
        self.evaluator.responses.append(evaluation())
        self.start()
        result = self.resume("Front-desk staff handle bookings and know the rules.")
        self.assertIn("Enter APPROVE", self.message(result))
        self.assertFalse(result["stakeholder_metadata"]["user_confirmed"])
        self.assertEqual(result["stakeholder_metadata"]["finalized_stakeholders"], [])
        result = self.resume("APPROVE")
        metadata = result["stakeholder_metadata"]
        self.assertTrue(metadata["user_confirmed"])
        self.assertEqual(len(metadata["finalized_stakeholders"]), 1)
        self.assertEqual(len(self.evaluator.calls), 1)

    def test_latest_exchange_survives_rebuilding_with_the_same_checkpointer(self):
        self.processor.responses.extend([
            response([draft(summary="", justification="")]),
            response([draft("Stakeholder-1")]),
        ])
        self.evaluator.responses.extend([evaluation(detail="not_met"), evaluation()])
        self.start()
        result = self.resume("Library staff")
        self.assertIn("More detail needed", self.message(result))
        last_prompt = self.message(result)
        previous_evaluation = result["stakeholder_metadata"]["evaluation"]
        self.graph = build_stakeholders(self.checkpointer)
        result = self.resume("They handle bookings and explain booking exceptions.")
        metadata = result["stakeholder_metadata"]
        self.assertEqual(metadata["drafts"][0]["stakeholder_id"], "Stakeholder-1")
        self.assertEqual(metadata["last_prompt_to_user"], last_prompt)
        self.assertNotIn("previous_evaluation", metadata)
        self.assertNotEqual(metadata["evaluation"], previous_evaluation)
        self.assertEqual(metadata["evaluation"]["provided_stakeholders"][0]["overall_verdict"],
                         "met")
        self.assertEqual(metadata["latest_user_response"],
                         "They handle bookings and explain booking exceptions.")
        self.assertNotIn("messages", metadata)
        self.assertIn(last_prompt, self.processor.calls[-1][-1].content)
        self.assertNotIn("<latest_evaluation>", self.evaluator.calls[-1][-1].content)
        self.assertNotIn("<last_prompt_to_user>", self.evaluator.calls[-1][-1].content)
        self.assertIn("Enter APPROVE", self.message(result))
        self.assertEqual(self.evaluator.calls[-1][1].content,
                         metadata["initial_context_message"])

    def test_model_input_does_not_accumulate_older_exchanges(self):
        first = evaluation(detail="not_met")
        first.provided_stakeholders[0].detail_feedback = "FIRST_EVALUATION_ONLY"
        second = evaluation(detail="not_met")
        second.provided_stakeholders[0].detail_feedback = "SECOND_EVALUATION_ONLY"
        self.processor.responses.extend([
            response([draft(summary="", justification="")]),
            response([draft("Stakeholder-1", justification="")]),
            response([draft("Stakeholder-1")]),
        ])
        self.evaluator.responses.extend([first, second, evaluation()])
        self.start()
        self.resume("Front-desk staff; initial note FIRST_USER_TURN_ONLY.")
        self.resume("They handle bookings; second-turn clarification.")
        result = self.resume("They know the booking rules and exceptions.")
        self.assertIn("Enter APPROVE", self.message(result))
        for model in (self.processor, self.evaluator):
            self.assertEqual([len(call) for call in model.calls], [3, 3, 3])
            self.assertIsInstance(model.calls[-1][0], SystemMessage)
            latest = "\n".join(m.content for m in model.calls[-1])
            self.assertNotIn("FIRST_USER_TURN_ONLY", latest)
            self.assertNotIn("FIRST_EVALUATION_ONLY", latest)
            if model is self.processor:
                self.assertIn("SECOND_EVALUATION_ONLY", latest)
                self.assertIn("They know the booking rules and exceptions.", latest)
            else:
                self.assertNotIn("SECOND_EVALUATION_ONLY", latest)
                self.assertNotIn("<user_response>", latest)
        self.assertEqual(result["stakeholder_metadata"]["drafts"][0]["stakeholder_id"], "Stakeholder-1")
        self.assertNotIn("messages", result["stakeholder_metadata"])

    def test_edits_at_confirmation_require_evaluation_and_new_confirmation(self):
        self.processor.responses.extend([
            response([draft()]),
            response([draft("Stakeholder-1", summary="Handle bookings and cancellations.")]),
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


    def test_empty_list_and_early_approve_do_not_finalize(self):
        self.processor.responses.append(response())
        self.evaluator.responses.append(evaluation(ids=()))
        self.start()
        result = self.resume("APPROVE")
        self.assertIn("Please provide at least one stakeholder", self.message(result))
        self.assertEqual(result["stakeholder_metadata"]["finalized_stakeholders"], [])

    def test_user_can_remove_and_add_groups_without_reusing_ids(self):
        self.processor.responses.extend([
            response([draft(), draft(name="University IT services", involvement="indirect")]),
            response([draft(name="Library management")], removed=["Stakeholder-2"]),
        ])
        self.evaluator.responses.extend([
            evaluation(ids=("Stakeholder-1", "Stakeholder-2")),
            evaluation(ids=("Stakeholder-1", "Stakeholder-3")),
        ])
        self.start()
        self.resume("Include front-desk staff and university IT services.")
        result = self.resume("Remove Stakeholder-2 and add library management.")
        metadata = result["stakeholder_metadata"]
        self.assertEqual([d["stakeholder_id"] for d in metadata["drafts"]],
                         ["Stakeholder-1", "Stakeholder-3"])
        self.assertEqual(metadata["next_draft_number"], 4)
        self.assertIn("Enter APPROVE", self.message(result))
        result = self.resume("APPROVE")
        self.assertEqual([d["name"] for d in result["stakeholder_metadata"]["finalized_stakeholders"]],
                         ["Front-desk library staff", "Library management"])

    def test_string_overlap_references_and_merge_preserve_the_remaining_id(self):
        overlapping = evaluation(ids=("Stakeholder-1", "Stakeholder-2"))
        first = overlapping.provided_stakeholders[0]
        first.overlap_verdict = "not_met"
        first.overlap_feedback = "Do these groups represent the same booking staff?"
        first.overlap_stakeholder_ids = ["Stakeholder-2"]
        self.processor.responses.extend([
            response([draft(), draft(name="Booking staff")]),
            response([draft("Stakeholder-1", name="Booking team")],
                     removed=["Stakeholder-2"]),
        ])
        self.evaluator.responses.extend([overlapping, evaluation()])
        self.start()
        result = self.resume("Include front-desk library staff and booking staff.")
        self.assertIn("Overlap with stakeholder(s) Stakeholder-2", self.message(result))
        result = self.resume("Merge Stakeholder-2 into Stakeholder-1 as Booking team.")
        self.assertIn("Enter APPROVE", self.message(result))
        result = self.resume("APPROVE")
        records = result["stakeholder_metadata"]["finalized_stakeholders"]
        self.assertEqual([r["stakeholder_id"] for r in records], ["Stakeholder-1"])
        self.assertEqual(records[0]["name"], "Booking team")

    def test_evaluator_cannot_skip_current_drafts(self):
        self.processor.responses.append(response([draft()]))
        self.evaluator.responses.extend([evaluation(ids=()), evaluation(ids=())])
        self.start()
        result = self.resume("Front-desk staff handle bookings.")
        self.assertIn("Enter RETRY", self.message(result))
        metadata = self.graph.get_state(self.config).values["stakeholder_metadata"]
        self.assertIsNone(metadata["evaluation"])
        self.assertFalse(metadata["user_confirmed"])

    def test_failed_reevaluation_keeps_feedback_but_cannot_finalize_edited_drafts(self):
        self.processor.responses.extend([
            response([draft()]),
            response([draft("Stakeholder-1", summary="Handle bookings and cancellations.")]),
        ])
        self.evaluator.responses.extend([evaluation(), evaluation(ids=()), evaluation(ids=())])
        self.start()
        result = self.resume("Front-desk staff handle bookings.")
        last_evaluation = result["stakeholder_metadata"]["evaluation"]
        result = self.resume("Add cancellations to Stakeholder-1.")
        self.assertIn("Enter RETRY", self.message(result))
        state = self.graph.get_state(self.config).values
        metadata = state["stakeholder_metadata"]
        self.assertEqual(metadata["evaluation"], last_evaluation)
        self.assertNotIn("previous_evaluation", metadata)
        self.assertIsNone(metadata["evaluated_draft_version"])
        self.assertEqual(metadata["draft_version"], 2)
        self.assertFalse(node.stakeholders_ready(state))
        with self.assertRaisesRegex(ValueError, "requires explicit approval"):
            node.finalize_stakeholders(state)

    def test_parent_graph_runs_sson_then_stakeholders_then_personas_and_ends(self):
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
        from agentic_flow.user_modelling.personas import node as persona_node
        from test_personas import draft as persona_draft, response as persona_response, evaluation as persona_evaluation
        persona_processor, persona_evaluator = StubModel(), StubModel()
        persona_processor.responses.append(persona_response([persona_draft()]))
        persona_evaluator.responses.append(persona_evaluation())
        for name, model in (("persona_response_processor", persona_processor),
                            ("persona_evaluator", persona_evaluator)):
            patcher = patch.object(persona_node, name, model)
            patcher.start()
            self.addCleanup(patcher.stop)
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
            self.assertIn("Let's describe personas", self.message(result))
            result = self.resume("Alex represents Stakeholder-1 and books rooms from a phone.")
            self.assertIn("Enter APPROVE", self.message(result))
            result = self.resume("APPROVE")

        self.assertNotIn("__interrupt__", result)
        self.assertEqual(result["intent_metadata"]["evaluation_of_statement"], "met")
        self.assertTrue(result["stakeholder_metadata"]["user_confirmed"])
        self.assertNotIn("intent_context", result["stakeholder_metadata"])
        self.assertEqual(result["captured_intent"], self.context)
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
        from agentic_flow.user_modelling.personas import node as persona_node
        from test_personas import draft as persona_draft, response as persona_response, evaluation as persona_evaluation
        persona_processor, persona_evaluator = StubModel(), StubModel()
        persona_processor.responses.append(persona_response([persona_draft()]))
        persona_evaluator.responses.append(persona_evaluation())
        for name, model in (("persona_response_processor", persona_processor),
                            ("persona_evaluator", persona_evaluator)):
            patcher = patch.object(persona_node, name, model)
            patcher.start()
            self.addCleanup(patcher.stop)
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
            self.assertIn("Let's describe personas", self.message(result))
            self.graph = build_ide3_chat(self.checkpointer)
            self.resume("Alex represents Stakeholder-1 and books rooms from a phone.")
            result = self.resume("APPROVE")
        self.assertNotIn("__interrupt__", result)
        self.assertEqual(len(result["persona_metadata"]["finalized_personas"]), 1)
        self.assertEqual(result["intent_metadata"]["attempt_number"], 2)
        self.assertEqual(len(result["stakeholder_metadata"]["finalized_stakeholders"]), 1)


if __name__ == "__main__":
    unittest.main()
