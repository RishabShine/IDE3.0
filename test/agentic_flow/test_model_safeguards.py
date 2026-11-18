"""Exercise malformed model output through real graphs and checkpoint resumes."""
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from langchain_core.exceptions import OutputParserException
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agentic_flow.user_modelling.personas import node as persona_node
from agentic_flow.user_modelling.personas.graph import build_personas
from agentic_flow.user_modelling.stakeholders import node as stakeholder_node
from agentic_flow.user_modelling.stakeholders.graph import build_stakeholders
from test_personas import draft as persona_draft, response as persona_response, evaluation as persona_evaluation
from test_stakeholders import draft, response, evaluation, StubModel


class Model(StubModel):
    def invoke(self, messages):
        result = super().invoke(messages)
        if isinstance(result, Exception):
            raise result
        return result


class ModelSafeguardTests(unittest.TestCase):
    @contextmanager
    def flow(self, area):
        personas = area == "persona"
        module = persona_node if personas else stakeholder_node
        build = build_personas if personas else build_stakeholders
        processor, evaluator = Model(), Model()
        saver = InMemorySaver()
        config = {"configurable": {"thread_id": str(uuid4())}}
        graph = build(saver)
        context = {"statement": "Self-service room booking", "benefits": ["Quick confirmation"]}
        state = {"captured_intent": context}
        if personas:
            state["stakeholder_metadata"] = {"finalized_stakeholders": [{
                "stakeholder_id": "Stakeholder-1", "name": "Students", "involvement": "direct",
                "summary": "Book rooms", "justification": "Need reliable room availability",
            }]}
        with (patch.object(module, area + "_response_processor", processor),
              patch.object(module, area + "_evaluator", evaluator)):
            graph.invoke(state, config)
            yield SimpleNamespace(
                processor=processor, evaluator=evaluator, graph=graph, saver=saver,
                config=config, build=build, module=module, context=context,
                draft=persona_draft if personas else draft,
                response=persona_response if personas else response,
                evaluation=persona_evaluation if personas else evaluation,
                id_field=area + "_id", metadata_key=area + "_metadata",
                prefix="Persona" if personas else "Stakeholder",
                resume=lambda text: graph.invoke(Command(resume=text), config),
            )

    def metadata(self, flow, result):
        return result[flow.metadata_key]

    def message(self, result):
        return result["__interrupt__"][0].value["prompt_to_user"]

    def test_first_submission_ids_are_application_assigned(self):
        for area in ("stakeholder", "persona"):
            with self.subTest(area=area), self.flow(area) as f:
                f.processor.responses.append(f.response([f.draft(f.prefix + "-99")]))
                f.evaluator.responses.append(f.evaluation())
                result = f.resume("Here is the first record.")
                self.assertEqual(self.metadata(f, result)["drafts"][0][f.id_field], f.prefix + "-1")
                self.assertIn("Quick confirmation", f.processor.calls[0][1].content)
                self.assertIn("Quick confirmation", f.evaluator.calls[0][1].content)

    def test_unknown_edit_is_corrected_without_adding_a_draft(self):
        for area in ("stakeholder", "persona"):
            with self.subTest(area=area), self.flow(area) as f:
                f.processor.responses.extend([
                    f.response([f.draft()]), f.response([f.draft("1", name="Edited")]),
                    f.response([f.draft(f.prefix + "-1", name="Edited")]),
                ])
                f.evaluator.responses.extend([f.evaluation(), f.evaluation()])
                f.resume("First record.")
                result = f.resume("Rename the record to Edited.")
                records = self.metadata(f, result)["drafts"]
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0][f.id_field], f.prefix + "-1")
                self.assertEqual(records[0]["name"], "Edited")
                self.assertIn("Valid IDs", f.processor.calls[-1][-1].content)
                self.assertIn("Rename the record", f.processor.calls[-1][-1].content)
                self.assertEqual(len(f.processor.calls[-1]), 3)

    def test_invalid_mixed_operations_are_atomic_and_recover_after_graph_reload(self):
        for area in ("stakeholder", "persona"):
            with self.subTest(area=area), self.flow(area) as f:
                f.processor.responses.append(f.response([f.draft()]))
                f.evaluator.responses.append(f.evaluation())
                first = f.resume("First record.")
                for _ in range(2):
                    f.processor.responses.append(f.response([
                        f.draft(f.prefix + "-1", name="Should not be saved"),
                        f.draft(f.prefix + "-99"),
                    ]))
                failed = f.resume("Change a record.")
                meta = self.metadata(f, failed)
                self.assertEqual(meta["drafts"], self.metadata(f, first)["drafts"])
                self.assertEqual(meta["draft_version"], self.metadata(f, first)["draft_version"])
                self.assertEqual(meta["model_error"]["stage"], "response")
                self.assertEqual(len(f.evaluator.calls), 1)
                self.assertIn("drafts are unchanged", self.message(failed))
                self.assertNotIn("Enter APPROVE", self.message(failed))
                f.processor.responses.append(f.response([f.draft(f.prefix + "-1", name="Edited")]))
                f.evaluator.responses.append(f.evaluation())
                rebuilt = f.build(f.saver)
                result = rebuilt.invoke(Command(resume="Rename the first record to Edited."), f.config)
                self.assertIsNone(self.metadata(f, result)["model_error"])
                self.assertIn("Enter APPROVE", self.message(result))

    def test_duplicate_additions_are_rejected_even_with_involvement_suffixes(self):
        for area in ("stakeholder", "persona"):
            with self.subTest(area=area), self.flow(area) as f:
                f.processor.responses.extend([f.response([
                    f.draft(name="Example group"), f.draft(name=" example GROUP (direct) "),
                ]) for _ in range(2)])
                failed = f.resume("First record.")
                meta = self.metadata(f, failed)
                self.assertEqual(meta["drafts"], [])
                self.assertEqual(meta["next_draft_number"], 1)
                self.assertIn("Duplicate draft names", meta["model_error"]["detail"])
                self.assertFalse(f.evaluator.calls)

    def test_removing_and_recreating_the_same_record_is_rejected(self):
        for area in ("stakeholder", "persona"):
            with self.subTest(area=area), self.flow(area) as f:
                f.processor.responses.append(f.response([f.draft()]))
                f.evaluator.responses.append(f.evaluation())
                first = f.resume("First record.")
                f.processor.responses.extend([
                    f.response([f.draft()], removed=[f.prefix + "-1"]) for _ in range(2)
                ])
                failed = f.resume("Remove that record.")
                meta = self.metadata(f, failed)
                self.assertEqual(meta["drafts"], self.metadata(f, first)["drafts"])
                self.assertIn("recreate", meta["model_error"]["detail"])

    def test_evaluation_corrects_removed_ids_and_preserves_gaps(self):
        for area in ("stakeholder", "persona"):
            with self.subTest(area=area), self.flow(area) as f:
                ids = tuple(f.prefix + "-" + str(i) for i in (1, 2, 3))
                f.processor.responses.extend([
                    f.response([f.draft(name=name) for name in ("One", "Two", "Three")]),
                    f.response(removed=[ids[1]]),
                ])
                f.evaluator.responses.extend([
                    f.evaluation(ids=ids), f.evaluation(ids=ids),
                    f.evaluation(ids=(ids[0], ids[2])),
                ])
                f.resume("Three records.")
                result = f.resume("Remove the second record.")
                self.assertEqual([d[f.id_field] for d in self.metadata(f, result)["drafts"]],
                                 [ids[0], ids[2]])
                self.assertIn("unexpected", f.evaluator.calls[-1][-1].content)
                self.assertIn("Enter APPROVE", self.message(result))

    def test_failed_evaluation_can_retry_without_another_response_processing_call(self):
        for area in ("stakeholder", "persona"):
            with self.subTest(area=area), self.flow(area) as f:
                f.processor.responses.append(f.response([f.draft()]))
                f.evaluator.responses.extend([f.evaluation(ids=()), f.evaluation(ids=()), f.evaluation()])
                failed = f.resume("First record.")
                meta = self.metadata(f, failed)
                self.assertEqual(meta["model_error"]["stage"], "evaluation")
                self.assertIsNone(meta["evaluated_draft_version"])
                self.assertIn("Enter RETRY", self.message(failed))
                result = f.resume("RETRY")
                self.assertEqual(len(f.processor.calls), 1)
                self.assertIsNone(self.metadata(f, result)["model_error"])
                self.assertIn("Enter APPROVE", self.message(result))

    def test_obsolete_fields_and_malformed_output_trigger_correction(self):
        for area in ("stakeholder", "persona"):
            with self.subTest(area=area), self.flow(area) as f:
                obsolete = f.response([f.draft()]).model_dump()
                obsolete["suggestion_decisions"] = []
                f.processor.responses.extend([obsolete, OutputParserException("Invalid JSON")])
                failed = f.resume("First record.")
                self.assertEqual(self.metadata(f, failed)["drafts"], [])
                self.assertIn("Extra inputs are not permitted", f.processor.calls[-1][-1].content)
                self.assertIn("Invalid JSON", self.metadata(f, failed)["model_error"]["detail"])
                self.assertFalse(f.evaluator.calls)

    def test_connection_failure_preserves_session_for_rephrased_reply(self):
        for area in ("stakeholder", "persona"):
            with self.subTest(area=area), self.flow(area) as f:
                f.processor.responses.append(ConnectionError("Model unavailable"))
                failed = f.resume("First record.")
                self.assertIn("drafts are unchanged", self.message(failed))
                self.assertEqual(len(f.processor.calls), 1)
                f.processor.responses.append(f.response([f.draft()]))
                f.evaluator.responses.append(f.evaluation())
                result = f.resume("Try this record again.")
                self.assertIn("Enter APPROVE", self.message(result))

    def test_invalid_related_reference_gets_corrected(self):
        for area in ("stakeholder", "persona"):
            with self.subTest(area=area), self.flow(area) as f:
                invalid = f.evaluation()
                if area == "stakeholder":
                    invalid.provided_stakeholders[0].overlap_stakeholder_ids = ["Stakeholder-99"]
                else:
                    invalid.provided_personas[0].inferred_stakeholder_id = "Stakeholder-99"
                f.processor.responses.append(f.response([f.draft()]))
                f.evaluator.responses.extend([invalid, f.evaluation()])
                result = f.resume("First record.")
                self.assertEqual(len(f.evaluator.calls), 2)
                self.assertIn("Enter APPROVE", self.message(result))

    def test_update_and_remove_same_id_never_applies_partial_operations(self):
        for area in ("stakeholder", "persona"):
            with self.subTest(area=area), self.flow(area) as f:
                f.processor.responses.append(f.response([f.draft()]))
                f.evaluator.responses.append(f.evaluation())
                first = f.resume("First record.")
                f.processor.responses.extend([f.response(
                    [f.draft(f.prefix + "-1", name="Changed")], removed=[f.prefix + "-1"]
                ) for _ in range(2)])
                failed = f.resume("Change the record.")
                self.assertEqual(self.metadata(f, failed)["drafts"], self.metadata(f, first)["drafts"])
                self.assertEqual(len(f.evaluator.calls), 1)
                self.assertIn("Do not update and remove", self.metadata(f, failed)["model_error"]["detail"])

    def test_missing_required_detail_cannot_pass_but_demographics_remain_optional(self):
        with self.flow("stakeholder") as f:
            f.processor.responses.append(f.response([f.draft(summary="")]))
            f.evaluator.responses.append(f.evaluation())
            result = f.resume("First record.")
            reviewed = self.metadata(f, result)["evaluation"]["provided_stakeholders"][0]
            self.assertEqual(reviewed["detail_verdict"], "not_met")
            self.assertEqual(reviewed["relevance_verdict"], "not_evaluated")
            self.assertNotIn("Enter APPROVE", self.message(result))
        with self.flow("persona") as f:
            f.processor.responses.append(f.response([f.draft(demographics="")]))
            f.evaluator.responses.append(f.evaluation(
                demographics_verdict="not_met", demographics_feedback="Provide an age."
            ))
            result = f.resume("First record; demographic details omitted.")
            reviewed = self.metadata(f, result)["evaluation"]["provided_personas"][0]
            self.assertEqual(reviewed["demographics_verdict"], "met")
            self.assertEqual(reviewed["demographics_feedback"], "")
            self.assertIn("Enter APPROVE", self.message(result))

    def test_question_only_does_not_create_records_or_approve_them(self):
        for area in ("stakeholder", "persona"):
            with self.subTest(area=area), self.flow(area) as f:
                f.processor.responses.extend([
                    f.response([f.draft()]), f.response(feedback="Which roles have different needs?"),
                ])
                f.evaluator.responses.extend([f.evaluation(), f.evaluation()])
                first = f.resume("First record.")
                result = f.resume("Should we split this group?")
                self.assertEqual(self.metadata(f, result)["drafts"], self.metadata(f, first)["drafts"])
                self.assertIn("Which roles have different needs?", self.message(result))
                self.assertNotIn("Enter APPROVE", self.message(result))

    def incomplete(self, flow, record_id=None, **changes):
        changes["summary" if flow.prefix == "Stakeholder" else "ksa"] = ""
        return flow.draft(record_id, **changes)

    def test_two_completed_refinements_allow_explicit_review_of_unresolved_checks(self):
        for area in ("stakeholder", "persona"):
            with self.subTest(area=area), self.flow(area) as f:
                f.processor.responses.extend([f.response([self.incomplete(f)]), f.response()])
                f.evaluator.responses.extend([f.evaluation(), f.evaluation()])
                first = f.resume("Here is the record, with some information missing.")
                self.assertEqual(self.metadata(f, first)["refinement_attempts"], 1)
                self.assertNotIn("Enter APPROVE", self.message(first))
                review = f.resume("That is all the information I have for now.")
                meta = self.metadata(f, review)
                self.assertEqual(meta["refinement_attempts"], 2)
                self.assertIn("Outstanding feedback", self.message(review))
                self.assertIn("Approval does not mark these checks as met", self.message(review))
                self.assertFalse(meta["user_confirmed"])
                self.assertEqual(meta["finalized_" + area + "s"], [])
                rebuilt = f.build(f.saver)
                final = rebuilt.invoke(Command(resume="APPROVE"), f.config)
                meta = self.metadata(f, final)
                self.assertTrue(meta["user_confirmed"])
                self.assertEqual(meta["evaluation"]["provided_" + area + "s"][0]["overall_verdict"], "not_met")
                self.assertEqual(len(meta["finalized_" + area + "s"]), 1)
                if area == "persona":
                    self.assertEqual(meta["finalized_personas"][0]["varied_justification"], "")

    def test_errors_and_corrective_retries_do_not_count_as_completed_refinements(self):
        for area in ("stakeholder", "persona"):
            with self.subTest(area=area), self.flow(area) as f:
                f.processor.responses.append(f.response([self.incomplete(f)]))
                f.evaluator.responses.extend([f.evaluation(ids=()), f.evaluation()])
                first = f.resume("Here is the first record.")
                self.assertEqual(self.metadata(f, first)["refinement_attempts"], 1)
                self.assertEqual(len(f.evaluator.calls), 2)
                f.processor.responses.extend([f.response([f.draft(f.prefix + "-99")]) for _ in range(2)])
                failed = f.resume("An edit the model misinterprets.")
                self.assertEqual(self.metadata(f, failed)["refinement_attempts"], 1)
                f.processor.responses.append(f.response())
                f.evaluator.responses.extend([f.evaluation(ids=()), f.evaluation(ids=())])
                failed = f.resume("Keep the current record.")
                self.assertEqual(self.metadata(f, failed)["refinement_attempts"], 1)
                self.assertIn("Enter RETRY", self.message(failed))
                f.evaluator.responses.append(f.evaluation())
                review = f.resume("RETRY")
                self.assertEqual(self.metadata(f, review)["refinement_attempts"], 2)
                self.assertIn("Outstanding feedback", self.message(review))

    def test_clarification_only_turns_do_not_consume_refinement_attempts(self):
        for area in ("stakeholder", "persona"):
            with self.subTest(area=area), self.flow(area) as f:
                f.processor.responses.append(f.response(feedback="Which role would you like to describe?"))
                question = f.resume("What do I enter here?")
                self.assertEqual(self.metadata(f, question)["refinement_attempts"], 0)
                self.assertFalse(f.evaluator.calls)
                self.assertIn("Which role", self.message(question))
                self.assertNotIn("Enter RETRY", self.message(question))
                f.processor.responses.append(f.response([self.incomplete(f)]))
                f.evaluator.responses.append(f.evaluation())
                f.resume("Here is a first record.")
                f.processor.responses.append(f.response(feedback="That field describes the group's role."))
                question = f.resume("What does that field mean?")
                self.assertEqual(self.metadata(f, question)["refinement_attempts"], 1)
                self.assertEqual(len(f.evaluator.calls), 1)
                self.assertIn("That field describes", self.message(question))

    def test_changing_bounded_readback_starts_a_new_round(self):
        for area in ("stakeholder", "persona"):
            with self.subTest(area=area), self.flow(area) as f:
                f.processor.responses.extend([
                    f.response([self.incomplete(f)]), f.response(),
                    f.response([self.incomplete(f, f.prefix + "-1", name="Changed role")]),
                ])
                f.evaluator.responses.extend([f.evaluation(), f.evaluation(), f.evaluation()])
                f.resume("First record.")
                f.resume("No more detail yet.")
                result = f.resume("Change the first record's name to Changed role.")
                self.assertEqual(self.metadata(f, result)["refinement_attempts"], 1)
                self.assertFalse(self.metadata(f, result)["user_confirmed"])
                self.assertNotIn("Enter APPROVE", self.message(result))

    def test_unknown_persona_link_blocks_approval_even_after_attempt_limit(self):
        with self.flow("persona") as f:
            f.processor.responses.extend([
                f.response([f.draft(stakeholder_id=None)]), f.response(),
                f.response([f.draft("Persona-1", stakeholder_id="Stakeholder-1")]),
            ])
            f.evaluator.responses.extend([
                f.evaluation(inferred_stakeholder_id="Stakeholder-1"),
                f.evaluation(inferred_stakeholder_id="Stakeholder-1"), f.evaluation(),
            ])
            f.resume("Alex, without a stakeholder link yet.")
            result = f.resume("No additional detail for now.")
            self.assertEqual(self.metadata(f, result)["refinement_attempts"], 2)
            self.assertNotIn("Enter APPROVE", self.message(result))
            self.assertIsNone(self.metadata(f, result)["drafts"][0]["stakeholder_id"])
            result = f.resume("Confirm Persona-1 represents Stakeholder-1.")
            self.assertIn("Enter APPROVE", self.message(result))

    def test_processor_gets_derived_targets_and_evaluator_gets_current_records_only(self):
        import json
        for area in ("stakeholder", "persona"):
            with self.subTest(area=area), self.flow(area) as f:
                changes = ({"detail_verdict": "not_met", "detail_feedback": "UNIQUE_QUESTION"}
                           if area == "stakeholder" else
                           {"ksa_verdict": "not_met", "ksa_feedback": "UNIQUE_QUESTION"})
                f.processor.responses.extend([
                    f.response([self.incomplete(f)]), f.response([f.draft(f.prefix + "-1")]),
                ])
                initial_evaluation = f.evaluation()
                item = getattr(initial_evaluation, "provided_" + area + "s")[0]
                for field, value in changes.items():
                    setattr(item, field, value)
                f.evaluator.responses.extend([initial_evaluation, f.evaluation()])
                f.resume("First record.")
                result = f.resume("UNIQUE_LATEST_REPLY")
                processor = f.processor.calls[-1][-1].content
                targets = json.loads(processor.split("<asked_about>")[1].split("</asked_about>")[0])
                self.assertEqual(targets, [f.prefix + "-1"])
                self.assertIn("UNIQUE_QUESTION", processor)
                self.assertIn("UNIQUE_LATEST_REPLY", processor)
                self.assertNotIn("<latest_evaluation>", processor)
                evaluator = f.evaluator.calls[-1][-1].content
                self.assertNotIn("UNIQUE_QUESTION", evaluator)
                self.assertNotIn("UNIQUE_LATEST_REPLY", evaluator)
                self.assertNotIn("<last_prompt_to_user>", evaluator)
                self.assertNotIn("<latest_evaluation>", evaluator)
                self.assertNotIn("asked_about", self.metadata(f, result))


if __name__ == "__main__":
    unittest.main()
