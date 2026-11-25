import json
import os
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, patch

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver

from agentic_flow.capture_intent.context_expected_benefits_current_situation import (
    node as context_node,
    prompts as context_prompts,
)
from agentic_flow.capture_intent.graph import build_capture_intent
from agentic_flow.capture_intent.sson import node as sson_node, prompts as sson_prompts
from agentic_flow.state import RED_FLAG, CapturedIntent
from agentic_flow.user_modelling.stakeholders import node as stakeholder_node
from agentic_flow.user_modelling.stakeholders.graph import build_stakeholders

PRD = """Library Group Study-Room Booking

Students email the front desk to request a room. Front-desk staff record requests
in a shared spreadsheet and send confirmation emails manually.

Staff spend about six hours a week answering booking emails. Two staff members can
edit the spreadsheet at the same time and accidentally book the same room twice.

The application should let students book rooms themselves from their phones.
Staff should spend less than one hour a week on booking emails, and a room must
never be double booked. More students will use the library in the evenings.

Everyone signs in with their MacID. The library always owns the study rooms.
Equipment loans are outside the scope of this project.
Student unhappiness with the booking process will not be addressed by this project."""

STATED_SSON ="The application should let students book rooms themselves from their phones."
SYNTHESIZED_SSON = ("Let students book library study rooms themselves from their phones, so "
                    "staff stop handling booking emails and rooms are never double booked.")


def criterion(verdict="met"):
    return {"verdict": verdict, "reason": "Because."}


def evaluation(*verdicts):
    names = ("clear_and_concise", "goal_and_how", "names_capability",
             "need_not_want", "success_condition")
    verdicts = verdicts or ("met",) * 5
    return {"criteria": {n: criterion(v) for n, v in zip(names, verdicts)},
            "feedback": "Clear need; add a deadline if there is one."}


def responses(**changes):
    """One canned model response per capture-intent call, all traceable to PRD."""
    canned = {
        "sson": {
            "stated_sson": None,
            "synthesized_sson": SYNTHESIZED_SSON,
            "evidence": ["Students email the front desk to request a room.",
                         "A sentence the PRD never says."],
            "what": "book rooms themselves", "how": "from their phones",
            "why": "staff spend hours on booking emails",
            "success_measure": "less than one hour a week on booking emails",
            "context_and_objective": "Bookings run through front-desk email today.",
        },
        "evaluation": evaluation(),
        "situation": {
            "current_situation": "Students email the front desk; staff use a spreadsheet.",
            "problems": [
                {"description": "Staff spend six hours a week on booking emails.",
                 "source": "Staff spend about six hours a week answering booking emails."},
                {"description": "Rooms get double booked.",
                 "source": "accidentally book the same room twice"},
                {"description": "Students are unhappy.",
                 "source": "Students are unhappy with the process."},  # not in the PRD
            ],
        },
        "benefits": {
            "benefits": [
                {"description": "Staff spend under an hour a week on booking emails.",
                 "source": "Staff should spend less than one hour a week on booking emails",
                 "addresses": ["Problem-1", "Problem-1", "Problem-99"],
                 "measure": "less than one hour a week"},
                {"description": "No room is double booked.",
                 "source": "a room must never be double booked",
                 "addresses": ["Problem-2"],
                 "measure": "zero double bookings per term"},  # not in the PRD
            ],
            "out_of_scope_problems": [
                {"problem_id": "Problem-3", "source": "Student unhappiness with the booking process will not be addressed by this project."},
                {"problem_id": "Problem-42", "source": "Student unhappiness with the booking process will not be addressed by this project."},  # no such problem
                # a real PRD quote, but it does not say the problem is out of scope
                {"problem_id": "Problem-1",
                  "source": "Staff spend about six hours a week answering booking emails."},
            ],
        },
        "environment": {
            "effects": [{"description": "More evening library use.",
                         "source": "More students will use the library in the evenings."}],
            "invariants": [{"description": "The library owns the rooms.",
                            "source": "The library always owns the study rooms."}],
            "constraints": [{"description": "MacID sign-in.",
                             "source": "Everyone signs in with their MacID."}],
            "scope_exclusions": [{"description": "Equipment loans.",
                                  "source": "Equipment loans are outside the scope of this project."}],
        },
    }
    canned.update(changes)
    return canned


@contextmanager
def patch_capture_intent(**changes):
    """Replace every capture-intent model with a Mock returning `responses()`."""
    canned = responses(**changes)
    targets = {
        "sson": (sson_node, "sson_extractor"),
        "evaluation": (sson_node, "sson_evaluator"),
        "situation": (context_node, "situation_extractor"),
        "benefits": (context_node, "benefit_extractor"),
        "environment": (context_node, "environment_extractor"),
    }
    models = {}
    with ExitStack() as stack:
        for key, (module, name) in targets.items():
            models[key] = Mock()
            models[key].invoke.return_value = canned[key]
            stack.enter_context(patch.object(module, name, models[key]))
        yield SimpleNamespace(**models)


def request(model) -> str:
    messages = model.invoke.call_args.args[0]
    assert isinstance(messages[0], SystemMessage) and isinstance(messages[1], HumanMessage)
    return messages[1].content


class CaptureIntentFlowTests(unittest.TestCase):
    def setUp(self):
        self.graph = build_capture_intent(InMemorySaver())
        self.config = {"configurable": {"thread_id": self.id()}}

    def run_graph(self, state=None, **changes):
        with patch_capture_intent(**changes) as models:
            result = self.graph.invoke(state or {"prd": PRD}, self.config)
        return result, models

    def test_runs_from_the_prd_alone_and_fills_every_captured_intent_field(self):
        result, models = self.run_graph()
        self.assertNotIn("__interrupt__", result)
        self.assertEqual(self.graph.get_state(self.config).next, ())
        captured = result["captured_intent"]
        self.assertEqual(set(captured), set(CapturedIntent.__annotations__))
        self.assertNotIn("intent_metadata", result)
        for model in vars(models).values():
            model.invoke.assert_called_once()
        self.assertEqual(self.graph.get_state(self.config).values["captured_intent"], captured)

    def test_synthesized_sson_is_red_flagged_and_keeps_only_traced_evidence(self):
        captured = self.run_graph()[0]["captured_intent"]
        self.assertEqual(captured["single_statement_intent"], f"{RED_FLAG} {SYNTHESIZED_SSON}")
        self.assertEqual(captured["sson_source"], "synthesized")
        self.assertEqual(captured["sson_evidence"],
                         ["Students email the front desk to request a room."])
        self.assertEqual(captured["what"], "book rooms themselves")
        self.assertEqual(captured["context_and_objective"],
                         "Bookings run through front-desk email today.")

    def test_sson_stated_in_the_prd_is_used_word_for_word_without_a_flag(self):
        sson = {**responses()["sson"], "stated_sson": STATED_SSON}
        captured = self.run_graph(sson=sson)[0]["captured_intent"]
        self.assertEqual(captured["single_statement_intent"], STATED_SSON)
        self.assertEqual(captured["sson_source"], "stated")

    def test_a_stated_sson_the_prd_does_not_contain_falls_back_to_the_flagged_synthesis(self):
        sson = {**responses()["sson"], "stated_sson": "Build the best booking app ever."}
        captured = self.run_graph(sson=sson)[0]["captured_intent"]
        self.assertTrue(captured["single_statement_intent"].startswith(RED_FLAG))
        self.assertEqual(captured["sson_source"], "synthesized")

    def test_sson_evaluation_is_scored_in_code_and_never_blocks(self):
        weak = evaluation("met", "partially_met", "met", "not_met", "met")
        result, models = self.run_graph(evaluation=weak)
        self.assertNotIn("__interrupt__", result)
        report = result["captured_intent"]["sson_evaluation"]
        self.assertEqual(report["score"], 70)
        self.assertFalse(report["passed"])
        self.assertEqual(report["criteria"]["need_not_want"]["verdict"], "not_met")
        self.assertIn("deadline", report["feedback"])
        # the evaluator judges the statement itself, not the flag
        self.assertIn(f"<sson>\n{SYNTHESIZED_SSON}\n</sson>", request(models.evaluation))
        self.assertIn("synthesized from the PRD", request(models.evaluation))

        strong = self.run_graph(evaluation=evaluation())[0]["captured_intent"]["sson_evaluation"]
        self.assertEqual((strong["score"], strong["passed"]), (100, True))

    def test_problems_get_ids_and_untraced_ones_are_flagged_not_dropped(self):
        captured = self.run_graph()[0]["captured_intent"]
        self.assertEqual(captured["current_situation"],
                         "Students email the front desk; staff use a spreadsheet.")
        problems = captured["problems"]
        self.assertEqual([p["id"] for p in problems], ["Problem-1", "Problem-2", "Problem-3"])
        self.assertEqual(problems[1]["source"], "accidentally book the same room twice")
        self.assertIsNone(problems[2]["source"])
        self.assertEqual(problems[2]["description"], f"{RED_FLAG} Students are unhappy.")
        self.assertFalse(problems[0]["description"].startswith(RED_FLAG))

    def test_a_quote_joining_separate_prd_sentences_is_still_traced(self):
        from agentic_flow.capture_intent.common import traced
        joined = ("Front-desk staff record requests in a shared spreadsheet and send "
                  "confirmation emails manually. Two staff members can edit the spreadsheet "
                  "at the same time and accidentally book the same room twice.")
        self.assertTrue(traced(joined, PRD))
        self.assertFalse(traced(joined + " Rooms are always free.", PRD))
        self.assertFalse(traced("", PRD))

    def test_a_real_quote_attached_to_the_wrong_item_is_flagged(self):
        from agentic_flow.capture_intent.common import supports
        targets = ("Staff should spend less than one hour a week on booking emails, and a "
                   "room must never be double booked.")
        self.assertTrue(supports(targets, "Staff spend under an hour a week on booking emails."))
        self.assertFalse(supports(targets, "Volunteer shifts move from packing on demand to batches."))
        self.assertTrue(supports("accidentally book the same room twice", "Rooms get double booked."))

    def test_benefit_measure_must_come_from_its_own_quote(self):
        benefits = {"benefits": [{
            "description": "No room is double booked.",
            "source": "a room must never be double booked",
            "addresses": ["Problem-2"],
            "measure": "less than one hour a week",  # in the PRD, but not in this quote
        }], "out_of_scope_problems": []}
        benefit = self.run_graph(benefits=benefits)[0]["captured_intent"]["benefits"][0]
        self.assertEqual(benefit["source"], "a room must never be double booked")
        self.assertEqual((benefit["measure"], benefit["kind"]), (None, "soft"))

    def test_food_bank_run_mismatched_benefits_are_flagged(self):
        """Replays the qwen2.5:7b benefit reply from the 2026-11-24 food-bank run."""
        targets = ("The food bank wants to cut average wait time to under 5 minutes, reduce "
                   "produce waste to under 10 kg a week, and serve at least 25% more students "
                   "per week within one term.")
        prd = (f"Lines often reach 40 minutes. {targets} We expect more students to use the "
               "food bank and fewer to skip meals before exams. Volunteer shifts will move "
               "from packing on demand to packing in batches.")
        benefits = {"benefits": [
            {"description": "more students to use the food bank and fewer to skip meals "
                            "before exams",
             "source": targets, "addresses": ["Problem-1"],
             "measure": "serve at least 25% more students per week within one term"},
            {"description": "Volunteer shifts will move from packing on demand to packing "
                            "in batches",
             "source": targets, "addresses": [], "measure": "no specific measure provided"},
        ], "out_of_scope_problems": []}
        captured = self.run_graph({"prd": prd}, benefits=benefits)[0]["captured_intent"]
        for benefit in captured["benefits"]:
            # the targets sentence is rejected as their quote, and so is its 25% measure;
            # both descriptions are PRD sentences, so they become their own quotes
            self.assertNotEqual(benefit["source"], targets)
            self.assertIn(benefit["source"], prd)
            self.assertEqual((benefit["measure"], benefit["kind"]), (None, "soft"))

        # once the environment step lists the same sentences as effects, each point is
        # kept once: "volunteer shifts" fixes no problem, so it is an effect only;
        # "more students" claims to fix Problem-1, so it stays a benefit
        effects = {"effects": [
            {"description": b["description"], "source": b["source"]} for b in benefits["benefits"]
        ], "invariants": [], "constraints": [], "scope_exclusions": []}
        captured = self.run_graph({"prd": prd}, benefits=benefits,
                                  environment=effects)[0]["captured_intent"]
        self.assertEqual([(b["id"], b["addresses"]) for b in captured["benefits"]],
                         [("Benefit-1", ["Problem-1"])])
        self.assertTrue(captured["benefits"][0]["description"].startswith("more students"))
        self.assertEqual(len(captured["effects"]), 1)
        self.assertEqual(captured["effects"][0]["id"], "Effect-1")
        self.assertTrue(captured["effects"][0]["description"].startswith("Volunteer shifts"))

    def test_food_bank_run_false_out_of_scope_is_dropped(self):
        """qwen2.5:7b marked the embarrassment problem out of scope; the PRD never says so."""
        quote = "Some students say they feel embarrassed waiting in a visible line."
        situation = {"current_situation": "", "problems": [
            {"description": "Students feel embarrassed waiting in line.", "source": quote}]}
        benefits = {"benefits": [], "out_of_scope_problems": [
            {"problem_id": "Problem-1", "source": quote}]}
        captured = self.run_graph({"prd": f"Lines are long. {quote}"}, situation=situation,
                                  benefits=benefits)[0]["captured_intent"]
        self.assertEqual(captured["out_of_scope_problems"], [])

    def test_out_of_scope_quote_must_be_about_that_problem(self):
        benefits = {**responses()["benefits"], "out_of_scope_problems": [
            {"problem_id": "Problem-2",
             "source": "Equipment loans are outside the scope of this project."}]}
        captured = self.run_graph(benefits=benefits)[0]["captured_intent"]
        self.assertEqual(captured["out_of_scope_problems"], [])

    def test_an_item_copied_from_the_prd_is_its_own_quote(self):
        """qwen2.5:7b quoted the anonymity sentence for two other, verbatim invariants."""
        anonymity = "The library keeps no record of who booked a room."
        prd = (f"{PRD}\n{anonymity} It will always serve walk-ins who did not book.")
        environment = {**responses()["environment"], "invariants": [
            {"description": "it will always serve walk-ins who did not book",
             "source": anonymity},
            {"description": "walk-ins are banned on weekends", "source": anonymity},
        ]}
        invariants = self.run_graph({"prd": prd}, environment=environment)[0][
            "captured_intent"]["invariants"]
        self.assertEqual(invariants[0]["source"], "it will always serve walk-ins who did not book")
        self.assertFalse(invariants[0]["description"].startswith(RED_FLAG))
        self.assertIsNone(invariants[1]["source"])
        self.assertTrue(invariants[1]["description"].startswith(RED_FLAG))

    def test_a_point_listed_as_benefit_and_effect_is_kept_once(self):
        """qwen2.5:7b listed 'more students use the food bank' as Benefit-4 and Effect-1."""
        effect = "More students will use the library in the evenings."
        benefits = {**responses()["benefits"]}
        benefits["benefits"] = [
            *benefits["benefits"],
            # soft, fixes nothing: really the effect, so it leaves the benefits
            {"description": "More students will use the library in the evenings.",
             "source": effect, "addresses": [], "measure": None},
        ]
        environment = {**responses()["environment"], "effects": [
            {"description": "More students will use the library in the evenings.",
             "source": effect},
            # same point as hard Benefit-1: the benefit stays, this effect goes
            {"description": "Staff spend under an hour a week on booking emails.",
             "source": "Staff should spend less than one hour a week on booking emails"},
        ]}
        captured = self.run_graph(benefits=benefits, environment=environment)[0]["captured_intent"]
        self.assertEqual([b["id"] for b in captured["benefits"]], ["Benefit-1", "Benefit-2"])
        self.assertNotIn("evenings", " ".join(b["description"] for b in captured["benefits"]))
        self.assertEqual([(e["id"], e["description"]) for e in captured["effects"]],
                         [("Effect-1", "More students will use the library in the evenings.")])

    def test_benefit_links_and_measures_are_checked_against_problems_and_prd(self):
        captured = self.run_graph()[0]["captured_intent"]
        first, second = captured["benefits"]
        self.assertEqual((first["id"], second["id"]), ("Benefit-1", "Benefit-2"))
        self.assertEqual(first["addresses"], ["Problem-1"])
        self.assertEqual((first["measure"], first["kind"]), ("less than one hour a week", "hard"))
        self.assertEqual((second["measure"], second["kind"]), (None, "soft"))
        self.assertEqual(second["addresses"], ["Problem-2"])
        self.assertEqual(captured["out_of_scope_problems"], ["Problem-3"])

    def test_environment_items_are_numbered_per_section(self):
        captured = self.run_graph()[0]["captured_intent"]
        self.assertEqual(captured["effects"][0]["id"], "Effect-1")
        self.assertEqual(captured["invariants"][0]["id"], "Invariant-1")
        self.assertEqual(captured["constraints"][0]["id"], "Constraint-1")
        self.assertEqual(captured["scope_exclusions"][0]["id"], "Exclusion-1")
        self.assertEqual(captured["constraints"][0]["source"],
                         "Everyone signs in with their MacID.")

    def test_empty_sections_stay_empty(self):
        empty = {"effects": [], "invariants": [], "constraints": [], "scope_exclusions": []}
        captured = self.run_graph(environment=empty)[0]["captured_intent"]
        for field in empty:
            self.assertEqual(captured[field], [])

    def test_each_step_sees_the_prd_and_what_earlier_steps_derived(self):
        _, models = self.run_graph()
        self.assertIn(PRD, request(models.sson))
        self.assertEqual(models.sson.invoke.call_args.args[0][0].content,
                         sson_prompts.SSON_EXTRACTION_INSTRUCTIONS)
        self.assertIn(f"{RED_FLAG} {SYNTHESIZED_SSON}", request(models.situation))
        self.assertEqual(models.situation.invoke.call_args.args[0][0].content,
                         context_prompts.CURRENT_SITUATION_INSTRUCTIONS)
        benefits_request = request(models.benefits)
        self.assertIn('"id": "Problem-2"', benefits_request)
        self.assertNotIn('"source"', benefits_request)  # ids and descriptions only
        self.assertIn('"id": "Benefit-1"', request(models.environment))
        for model in vars(models).values():
            self.assertIn(PRD, request(model))

    def test_keeps_captured_intent_fields_from_other_steps(self):
        result, _ = self.run_graph({"prd": PRD, "captured_intent": {"goals": ["Keep me"]}})
        self.assertEqual(result["captured_intent"]["goals"], ["Keep me"])

    def test_requires_a_prd(self):
        with patch_capture_intent() as models, self.assertRaises(ValueError):
            self.graph.invoke({"prd": "   "}, self.config)
        models.sson.invoke.assert_not_called()


class CaptureIntentToStakeholdersTests(unittest.TestCase):
    def test_stakeholder_extraction_receives_the_full_captured_intent(self):
        with patch_capture_intent():
            captured = build_capture_intent(InMemorySaver()).invoke(
                {"prd": PRD}, {"configurable": {"thread_id": "intent"}}
            )

        extractor = Mock()
        extractor.invoke.return_value = {"stakeholders": [
            {"name": "Front-desk staff", "involvement": "direct",
             "summary": "Handle bookings.", "justification": "Know the booking rules."},
        ]}
        with patch.object(stakeholder_node, "stakeholder_extractor", extractor):
            result = build_stakeholders(InMemorySaver()).invoke(
                captured, {"configurable": {"thread_id": "stakeholders"}}
            )

        self.assertEqual(result["stakeholder_metadata"]["stakeholders"][0]["stakeholder_id"],
                         "Stakeholder-1")
        sent = extractor.invoke.call_args.args[0][1].content
        self.assertIn(json.dumps(captured["captured_intent"], ensure_ascii=False), sent)
        for text in ("Problem-1", "Benefit-1", "less than one hour a week", "Constraint-1"):
            self.assertIn(text, sent)

    def test_saved_chat_output_is_a_ready_stakeholders_input(self):
        from agentic_flow.capture_intent.chat_utils import save_stakeholder_input
        with patch_capture_intent():
            result = build_capture_intent(InMemorySaver()).invoke(
                {"prd": PRD}, {"configurable": {"thread_id": "intent"}}
            )
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "intent.json")
            save_stakeholder_input(path, result)
            with open(path, encoding="utf-8") as f:
                saved = json.load(f)

        self.assertEqual(set(saved), {"prd", "captured_intent"})
        self.assertEqual(saved["captured_intent"], result["captured_intent"])
        extractor = Mock()
        extractor.invoke.return_value = {"stakeholders": []}
        with patch.object(stakeholder_node, "stakeholder_extractor", extractor):
            build_stakeholders(InMemorySaver()).invoke(
                saved, {"configurable": {"thread_id": "from-file"}}
            )
        self.assertIn(json.dumps(saved["captured_intent"], ensure_ascii=False),
                      extractor.invoke.call_args.args[0][1].content)


if __name__ == "__main__":
    unittest.main()
