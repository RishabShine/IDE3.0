import unittest
from collections import deque
from unittest.mock import patch

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agentic_flow.user_modelling.personas import node, prompt
from agentic_flow.user_modelling.personas.graph import build_personas
from agentic_flow.user_modelling.personas.schema import (
    IndividualPersonaEvaluation,
    PersonaDraftUpdate,
    PersonaEvaluation,
    PersonaResponse,
    PersonaSuggestionDecision,
    SuggestedPersona,
)


class StubModel:
    def __init__(self):
        self.responses = deque()
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("Unexpected model call")
        return self.responses.popleft()


def draft(persona_id=None, **changes):
    return PersonaDraftUpdate(**{
        "persona_id": persona_id,
        "stakeholder_id": "Stakeholder-1",
        "name": "Alex",
        "role": "Student room-booker",
        "status_and_trust_level": "Enrolled student with university credentials.",
        "demographics": "",
        "ksa": "Comfortable with a phone, unfamiliar with booking rules.",
        "gmc": "Needs a confirmed room without waiting for staff email.",
        "usage_patterns": "Books from a phone between classes several times a week.",
        **changes,
    })


def response(updates=(), decisions=(), removed=(), feedback=""):
    return PersonaResponse(
        updates=list(updates), removed_persona_ids=list(removed),
        suggestion_decisions=list(decisions), clarification_feedback=feedback,
    )


def evaluation(ids=("Persona-1",), suggestions=(), **changes):
    fields = ["relevance", *prompt.PERSONA_FIELD_LABELS, "varied"]
    verdicts = {f + "_verdict": "met" for f in fields}
    feedback = {f + "_feedback": "" for f in fields}
    return PersonaEvaluation(
        provided_personas=[IndividualPersonaEvaluation(**{
            "persona_id": persona_id,
            **verdicts, **feedback,
            "inferred_stakeholder_id": None,
            "varied_justification": (
                "Vivid: Alex has a concrete role. Actionable: booking guidance matters. "
                "Real: grounded in the supplied profile. Identifiable: needs quick confirmation. "
                "Exact: student room-bookers. Detailed: phone use between classes."
            ),
            "overall_verdict": "met",
            **changes,
        }) for persona_id in ids],
        suggested_personas=list(suggestions),
    )


class PersonaFlowTests(unittest.TestCase):
    def setUp(self):
        self.processor, self.evaluator = StubModel(), StubModel()
        for name, model in (("persona_response_processor", self.processor),
                            ("persona_evaluator", self.evaluator)):
            patcher = patch.object(node, name, model)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.checkpointer = InMemorySaver()
        self.graph = build_personas(self.checkpointer)
        self.config = {"configurable": {"thread_id": self.id()}}
        self.state = {"stakeholder_metadata": {"finalized_stakeholders": [
            {"stakeholder_id": "Stakeholder-1", "name": "Students",
             "involvement": "direct", "summary": "Book rooms.",
             "justification": "Use the booking service."},
            {"stakeholder_id": "Stakeholder-2", "name": "Library staff",
             "involvement": "direct", "summary": "Manage bookings.",
             "justification": "Handle exceptions."},
        ]}}
        self.suggestion = SuggestedPersona(
            stakeholder_id="Stakeholder-1", description="Infrequent room-booker",
            justification="Needs more guidance than frequent users.",
        )

    def start(self):
        return self.graph.invoke(self.state, self.config)

    def resume(self, text):
        return self.graph.invoke(Command(resume=text), self.config)

    def message(self, result):
        return result["__interrupt__"][0].value["prompt_to_user"]

    def test_starter_uses_finalized_stakeholders_and_waits_without_model_calls(self):
        result = self.start()
        self.assertIn("Stakeholder-1", self.message(result))
        self.assertIn("Library staff", self.message(result))
        self.assertFalse(self.processor.calls)
        self.assertNotIn("persona_metadata", self.graph.get_state(self.config).values)
        self.processor.responses.append(response([draft()]))
        self.evaluator.responses.append(evaluation())
        result = self.resume("Alex is a student who books rooms from a phone.")
        metadata = result["persona_metadata"]
        self.assertIn('"stakeholder_id": "Stakeholder-1"', metadata["initial_context_message"])
        self.assertIn("<captured_intent>\n{}\n</captured_intent>", metadata["initial_context_message"])
        self.assertNotIn("intent_context", metadata)
        self.assertEqual(result["stakeholder_metadata"], self.state["stakeholder_metadata"])

    def test_requires_finalized_stakeholders(self):
        with self.assertRaisesRegex(ValueError, "finalized stakeholders first"):
            self.graph.invoke({}, self.config)

    def test_optional_demographics_passes_and_finalization_requires_approval(self):
        self.processor.responses.append(response([draft(varied_justification="UNTRUSTED")]))
        self.evaluator.responses.append(evaluation())
        self.start()
        result = self.resume("Here is Alex's profile.")
        self.assertIn("Enter APPROVE", self.message(result))
        metadata = result["persona_metadata"]
        self.assertFalse(metadata["user_confirmed"])
        self.assertEqual(metadata["finalized_personas"], [])
        self.assertEqual(metadata["drafts"][0]["demographics"], "")
        self.assertNotIn("UNTRUSTED", self.evaluator.calls[0][-1].content)
        with self.assertRaisesRegex(ValueError, "explicit approval"):
            node.finalize_personas(result)
        result = self.resume("APPROVE")
        metadata = result["persona_metadata"]
        self.assertEqual(metadata["approved_version"], metadata["draft_version"])
        self.assertEqual(metadata["finalized_personas"], metadata["drafts"])
        self.assertIn("Vivid:", metadata["finalized_personas"][0]["varied_justification"])
        self.assertNotIn("__interrupt__", result)
        self.assertEqual(self.graph.get_state(self.config).next, ())

    def test_inferred_link_needs_confirmation_and_gates_other_checks(self):
        self.processor.responses.extend([
            response([draft(stakeholder_id=None)]), response([draft("Persona-1")]),
        ])
        self.evaluator.responses.extend([
            evaluation(inferred_stakeholder_id="Stakeholder-1", ksa_feedback="SHOULD_BE_HIDDEN"),
            evaluation(),
        ])
        self.start()
        result = self.resume("Alex books rooms.")
        metadata = result["persona_metadata"]
        self.assertIsNone(metadata["drafts"][0]["stakeholder_id"])
        reviewed = metadata["evaluation"]["provided_personas"][0]
        self.assertEqual(reviewed["relevance_verdict"], "not_evaluated")
        self.assertEqual(reviewed["ksa_verdict"], "not_evaluated")
        self.assertEqual(reviewed["ksa_feedback"], "")
        self.assertEqual(metadata["drafts"][0]["varied_justification"], "")
        self.assertIn("Proposed link: Stakeholder-1", self.message(result))
        self.assertNotIn("SHOULD_BE_HIDDEN", self.message(result))
        result = self.resume("Confirm Persona-1 represents Stakeholder-1.")
        self.assertIn("Enter APPROVE", self.message(result))
        self.assertEqual(result["persona_metadata"]["drafts"][0]["stakeholder_id"], "Stakeholder-1")

    def test_unknown_explicit_link_cannot_pass_even_if_model_passes_it(self):
        self.processor.responses.append(response([draft(stakeholder_id="Stakeholder-99")]))
        self.evaluator.responses.append(evaluation())
        self.start()
        result = self.resume("Alex represents Stakeholder-99.")
        reviewed = result["persona_metadata"]["evaluation"]["provided_personas"][0]
        self.assertEqual(reviewed["relevance_verdict"], "not_met")
        self.assertEqual(reviewed["varied_verdict"], "not_evaluated")
        self.assertFalse(node.personas_ready(result))
        self.assertIn("select a finalized stakeholder ID", self.message(result))

    def test_suggestion_acceptance_creates_partial_draft_not_a_varied_pass(self):
        self.processor.responses.extend([
            response([draft()]), response(decisions=[PersonaSuggestionDecision(
                **self.suggestion.model_dump(exclude={"justification"}), decision="accept", reason=""
            )]),
        ])
        self.evaluator.responses.extend([
            evaluation(suggestions=[self.suggestion]),
            evaluation(ids=("Persona-1", "Persona-2")),
        ])
        self.start()
        self.resume("Alex books rooms frequently.")
        result = self.resume("Include the infrequent room-booker suggestion.")
        metadata = result["persona_metadata"]
        proposed = metadata["drafts"][1]
        self.assertEqual(proposed["persona_id"], "Persona-2")
        self.assertEqual(proposed["role"], self.suggestion.description)
        self.assertEqual(proposed["stakeholder_id"], "Stakeholder-1")
        self.assertEqual(proposed["varied_justification"], "")
        self.assertEqual(metadata["pending_suggestions"], [])
        self.assertIn("Personas needing refinement", self.message(result))
        self.assertNotIn("Enter APPROVE", self.message(result))

    def test_declined_and_unanswered_suggestions_remain_distinct_by_stakeholder(self):
        other = self.suggestion.model_copy(update={"stakeholder_id": "Stakeholder-2"})
        self.processor.responses.extend([
            response([draft()]), response(decisions=[PersonaSuggestionDecision(
                stakeholder_id="Stakeholder-1", description=self.suggestion.description,
                decision="decline", reason="Already covered."
            )]), response(decisions=[PersonaSuggestionDecision(
                stakeholder_id="Stakeholder-2", description=other.description,
                decision="decline", reason="Not needed."
            )]),
        ])
        self.evaluator.responses.extend([
            evaluation(suggestions=[self.suggestion, other]),
            evaluation(suggestions=[self.suggestion]), evaluation(suggestions=[other]),
        ])
        self.start()
        self.resume("Alex books rooms.")
        result = self.resume("Decline the suggestion for Stakeholder-1; leave the other undecided.")
        metadata = result["persona_metadata"]
        self.assertEqual(metadata["pending_suggestions"], [other.model_dump()])
        self.assertEqual(metadata["declined_suggestions"][0]["reason"], "Already covered.")
        self.assertNotIn("Enter APPROVE", self.message(result))
        result = self.resume("Decline the remaining suggestion.")
        self.assertEqual(result["persona_metadata"]["pending_suggestions"], [])
        self.assertIn("Enter APPROVE", self.message(result))
        latest = self.evaluator.calls[-1][-1].content
        self.assertIn("Already covered.", latest)
        self.assertIn("Not needed.", latest)

    def test_confirmation_edit_clears_rationale_and_requires_fresh_approval(self):
        self.processor.responses.extend([
            response([draft()]), response([draft("Persona-1", gmc="Needs cancellation guidance.",
                                                 varied_justification="STALE_RATIONALE")]),
        ])
        self.evaluator.responses.extend([
            evaluation(), evaluation(varied_justification="NEW_RATIONALE based on the edited profile."),
        ])
        self.start()
        first = self.resume("Alex books rooms.")
        old_version = first["persona_metadata"]["draft_version"]
        result = self.resume("Change Persona-1's needs to cancellation guidance.")
        metadata = result["persona_metadata"]
        self.assertGreater(metadata["draft_version"], old_version)
        self.assertEqual(metadata["evaluated_draft_version"], metadata["draft_version"])
        self.assertFalse(metadata["user_confirmed"])
        # The evaluator sees old verdicts as context, but no cached rationale in the edited draft.
        import json
        turn = self.evaluator.calls[-1][-1].content
        current = json.loads(turn.split("<personas>")[1].split("</personas>")[0])
        self.assertEqual(current[0]["varied_justification"], "")
        self.assertIn("NEW_RATIONALE", self.message(result))
        result = self.resume("APPROVE")
        self.assertEqual(result["persona_metadata"]["finalized_personas"][0]["persona_id"], "Persona-1")

    def test_resume_keeps_latest_exchange_without_growing_message_history(self):
        self.processor.responses.extend([
            response([draft(ksa="")]), response([draft("Persona-1", gmc="")]),
            response([draft("Persona-1")]),
        ])
        self.evaluator.responses.extend([
            evaluation(ksa_verdict="not_met", ksa_feedback="FIRST_FEEDBACK_ONLY"),
            evaluation(gmc_verdict="not_met", gmc_feedback="SECOND_FEEDBACK_ONLY"), evaluation(),
        ])
        self.start()
        self.resume("FIRST_USER_ONLY: Alex is a student.")
        self.graph = build_personas(self.checkpointer)
        self.resume("They use a phone comfortably.")
        result = self.resume("They need quick booking confirmation.")
        self.assertIn("Enter APPROVE", self.message(result))
        for model in (self.processor, self.evaluator):
            self.assertEqual([len(call) for call in model.calls], [3, 3, 3])
            latest = "\n".join(message.content for message in model.calls[-1])
            self.assertNotIn("FIRST_USER_ONLY", latest)
            self.assertNotIn("FIRST_FEEDBACK_ONLY", latest)
            self.assertIn("SECOND_FEEDBACK_ONLY", latest)
            self.assertIn("They need quick booking confirmation.", latest)
        self.assertNotIn("messages", result["persona_metadata"])
        self.assertNotIn("previous_evaluation", result["persona_metadata"])

    def test_failed_reevaluation_cannot_approve_an_edited_profile(self):
        self.processor.responses.extend([
            response([draft()]), response([draft("Persona-1", gmc="Changed needs.")]),
        ])
        self.evaluator.responses.extend([evaluation(), evaluation(ids=())])
        self.start()
        self.resume("Alex books rooms.")
        with self.assertRaisesRegex(ValueError, "each current draft exactly once"):
            self.resume("Change Persona-1's needs.")
        state = self.graph.get_state(self.config).values
        self.assertFalse(node.personas_ready(state))
        self.assertEqual(state["persona_metadata"]["drafts"][0]["varied_justification"], "")
        with self.assertRaisesRegex(ValueError, "explicit approval"):
            node.finalize_personas(state)

    def test_removal_suppresses_resuggestion_and_does_not_reuse_ids(self):
        removed = SuggestedPersona(stakeholder_id="Stakeholder-1",
                                   description="Infrequent room-booker", justification="Different needs.")
        self.processor.responses.extend([
            response([draft(), draft(name="Sam", role=removed.description)]),
            response([draft(name="Robin")], removed=["Persona-2"]),
        ])
        self.evaluator.responses.extend([
            evaluation(ids=("Persona-1", "Persona-2")),
            evaluation(ids=("Persona-1", "Persona-3"), suggestions=[removed]),
        ])
        self.start()
        self.resume("Include Alex and Sam.")
        result = self.resume("Remove Persona-2 and add Robin.")
        metadata = result["persona_metadata"]
        self.assertEqual([d["persona_id"] for d in metadata["drafts"]], ["Persona-1", "Persona-3"])
        self.assertEqual(metadata["pending_suggestions"], [])
        self.assertEqual(metadata["next_draft_number"], 4)

    def test_empty_list_and_early_approval_do_not_finalize(self):
        self.processor.responses.append(response())
        self.evaluator.responses.append(evaluation(ids=()))
        self.start()
        result = self.resume("APPROVE")
        self.assertIn("Please provide at least one persona", self.message(result))
        self.assertEqual(result["persona_metadata"]["finalized_personas"], [])


if __name__ == "__main__":
    unittest.main()
