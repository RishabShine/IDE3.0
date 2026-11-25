"""Impact analysis agent: candidate selection, validation, and the review flow."""
import copy
import tempfile
import time
import unittest
from unittest import mock

from fastapi.testclient import TestClient

import replay
from agentic_flow.api import pipeline
from agentic_flow.api.server import create_app
from agentic_flow.api.store import Store
from agentic_flow.impact_analysis import node
from agentic_flow.impact_analysis.graph import build_impact_analysis
from replay import SAMPLE_PRD


def food_bank_state() -> dict:
    state = {"prd": SAMPLE_PRD}
    with replay.replay_models():
        pipeline.run_full(state, state.update, lambda n: None)
    return state


BASE = None


def setUpModule():
    global BASE
    BASE = food_bank_state()


def assessed(*rows, new=()):
    return {"assessments": [{"artifact_id": a, "verdict": v, "reason": r, "changes": c}
                            for a, v, r, c in rows],
            "new_artifacts": list(new)}


class StubModel:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def invoke(self, messages):
        self.calls.append(messages)
        return self.reply(messages) if callable(self.reply) else self.reply


class AgentTests(unittest.TestCase):
    def run_agent(self, changes, reply, state=None):
        model = StubModel(reply)
        with mock.patch.object(node, "impact_model", model):
            result = build_impact_analysis().invoke(
                {**copy.deepcopy(state or BASE), "impact_request": {"changes": changes}})
        return result["impact_report"], model

    def candidate_ids(self, report):
        return [c["id"] for c in report["candidates"]]

    def test_candidates_follow_trace_links_two_steps_but_not_past_the_intent(self):
        report, model = self.run_agent(
            [{"key": "problems:Problem-2", "action": "edited", "before": {}, "after": {}}],
            assessed())
        ids = self.candidate_ids(report)
        self.assertIn("Benefit-2", ids)          # Benefit-2 addresses Problem-2
        self.assertIn("Goal-2", ids)             # Goal-2 delivers Benefit-2
        self.assertIn("Intent-1", ids)           # Problem-2 motivates the intent
        self.assertNotIn("Problem-2", ids)       # what changed is not a candidate
        self.assertNotIn("Stakeholder-1", ids)   # only reachable through the intent
        benefit = next(c for c in report["candidates"] if c["id"] == "Benefit-2")
        self.assertIn("Benefit-2 addresses Problem-2", benefit["linked_because"])
        self.assertEqual(set(benefit["revisable_fields"]), {"description", "measure"})
        self.assertIn("Problem-2", model.calls[0][1].content)

    def test_an_sson_edit_reaches_its_direct_links_only(self):
        report, _ = self.run_agent(
            [{"key": "singleton:sson", "action": "edited", "before": {}, "after": {}}], assessed())
        types = {c["type"] for c in report["candidates"]}
        self.assertEqual(types, {"problem", "benefit", "stakeholder", "goal"})

    def test_deleting_proposes_unlinking_without_the_model(self):
        report, _ = self.run_agent(
            [{"key": "benefits:Benefit-1", "action": "deleted", "before": {}, "after": None}],
            assessed())
        unlink = [p for p in report["proposals"] if p["kind"] == "unlink"]
        self.assertEqual([(p["artifact_id"], p["fields"]) for p in unlink],
                         [("Goal-1", {"benefit_ids": []})])
        self.assertEqual(unlink[0]["before"], {"benefit_ids": ["Benefit-1"]})

    def test_validation_turns_assessments_into_proposals_and_notes(self):
        reply = assessed(
            ("Benefit-2", "revise", "Waste target changed.",
             [{"field": "description", "value": "reduce produce waste to under 5 kg a week"},
              {"field": "addresses", "value": "Problem-9"}]),
            ("Goal-2", "obsolete", "Only existed for the old target.", []),
            ("UC-4", "revise", "Volunteers no longer need it.", []),
            ("Intent-1", "obsolete", "Intent cannot be removed.", []),
            ("Nope-1", "revise", "Not a candidate.", []),
            new=[{"type": "constraint", "text": "Weigh produce weekly.", "reason": "New target."}])
        report, _ = self.run_agent(
            [{"key": "problems:Problem-2", "action": "edited", "before": {}, "after": {}}], reply)
        kinds = {(p["kind"], p["artifact_id"]) for p in report["proposals"]}
        self.assertIn(("revise", "Benefit-2"), kinds)
        self.assertIn(("remove", "Goal-2"), kinds)
        self.assertIn(("add", None), kinds)
        revise = next(p for p in report["proposals"] if p["kind"] == "revise")
        self.assertEqual(revise["fields"], {"description": "reduce produce waste to under 5 kg a week"})
        self.assertEqual(revise["before"], {"description": "reduce produce waste to under 10 kg a week"})
        add = next(p for p in report["proposals"] if p["kind"] == "add")
        self.assertEqual((add["collection"], add["fields"]),
                         ("constraints", {"description": "Weigh produce weekly."}))
        notes = " | ".join(report["notes"])
        self.assertIn("'addresses' cannot be revised", notes)
        self.assertIn("Nope-1, which was not a candidate", notes)
        # UC-4 is three links from Problem-2 (benefit, goal, use case): not a candidate
        self.assertIn("UC-4, which was not a candidate", notes)
        self.assertIn("Intent-1 was marked obsolete without a usable edit", notes)
        unaffected = {u["artifact_id"]: u["reason"] for u in report["unaffected"]}
        self.assertEqual(unaffected["Problem-1"] if "Problem-1" in unaffected else
                         "Not assessed by the model.", "Not assessed by the model.")
        self.assertEqual([p["proposal_id"] for p in report["proposals"]],
                         [f"P-{n}" for n in range(1, len(report["proposals"]) + 1)])

    def test_affected_use_cases_become_one_rebuild_suggestion(self):
        reply = assessed(("UC-1", "revise", "Booking changed.", []),
                         ("UC-5", "obsolete", "No hand-out any more.", []))
        report, _ = self.run_agent(
            [{"key": "goals:Goal-1", "action": "edited", "before": {}, "after": {}}], reply)
        self.assertIn("UC-1", self.candidate_ids(report))  # UC-1 achieves Goal-1
        reruns = [p for p in report["proposals"] if p["kind"] == "rerun"]
        self.assertEqual(len(reruns), 1)
        self.assertEqual(reruns[0]["stage"], "use_cases")
        self.assertIn("UC-1: Booking changed.", reruns[0]["reason"])
        self.assertIn("use_cases", report["stages"])

    def test_no_candidates_means_no_model_call(self):
        state = {"prd": "x", "captured_intent": {}}
        report, model = self.run_agent(
            [{"key": "effects:Effect-9", "action": "edited", "before": {}, "after": {}}],
            assessed(), state=state)
        self.assertEqual((report["candidates"], report["proposals"]), ([], []))
        self.assertEqual(model.calls, [])


class ReviewFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        models = replay.replay_models()
        models.__enter__()
        self.addCleanup(models.__exit__, None, None, None)
        self.client = TestClient(create_app(Store(self.tmp.name)))
        self.sid = self.call("POST", "/api/sessions", {"prd": SAMPLE_PRD})["id"]
        self.wait()

    def call(self, method, path, body=None, status=200):
        response = self.client.request(method, path, json=body)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def url(self, suffix=""):
        return f"/api/sessions/{self.sid}{suffix}"

    def wait(self):
        for _ in range(200):
            session = self.call("GET", self.url())
            if not session["running"]:
                return session
            time.sleep(0.05)
        self.fail("still running")

    def test_edit_analyze_accept_reject_close(self):
        self.call("POST", self.url("/impact"), status=422)  # nothing edited yet
        self.call("PATCH", self.url("/items/problems/Problem-2"),
                  {"fields": {"description": "About 20 kg of produce is thrown out every week."}})
        session = self.call("GET", self.url())
        self.assertEqual([c["key"] for c in session["changes"]], ["problems:Problem-2"])
        self.assertEqual(session["stages"]["goals"]["status"], "stale")

        self.call("POST", self.url("/impact"))
        session = self.wait()
        report = session["impact_reports"][0]
        self.assertEqual((report["report_id"], report["status"]), ("R-1", "open"))
        self.assertEqual(session["changes"][0]["analyzed_in"], "R-1")
        revise = next(p for p in report["proposals"] if p["kind"] == "revise")
        self.assertTrue(revise["fields"])

        session = self.call("POST", self.url(f"/impact/R-1/proposals/{revise['proposal_id']}"),
                            {"decision": "accept"})
        record = session["items"][revise["key"]]
        self.assertEqual(record["status"], "edited")
        # the applied suggestion does not become a new edit to analyze
        self.assertTrue(all(c["analyzed_in"] == "R-1" for c in session["changes"]))
        self.call("POST", self.url(f"/impact/R-1/proposals/{revise['proposal_id']}"),
                  {"decision": "reject"}, status=409)

        session = self.call("POST", self.url("/impact/R-1/close"))
        self.assertEqual(session["impact_reports"][0]["status"], "closed")
        for stage in session["impact_reports"][0]["stages"]:
            self.assertNotEqual(session["stages"][stage]["status"], "stale")
        self.call("POST", self.url("/impact"), status=422)

    def test_deleting_then_accepting_the_unlink_suggestion(self):
        self.call("DELETE", self.url("/items/benefits/Benefit-1"))
        self.call("POST", self.url("/impact"))
        report = self.wait()["impact_reports"][0]
        unlink = next(p for p in report["proposals"] if p["kind"] == "unlink")
        session = self.call("POST", self.url(f"/impact/R-1/proposals/{unlink['proposal_id']}"),
                            {"decision": "accept"})
        goal = next(g for g in session["state"]["goal_metadata"]["goals"] if g["goal_id"] == "Goal-1")
        self.assertEqual(goal["benefit_ids"], [])
        kinds = {g["kind"] for g in session["state"]["artifact_graph"]["gaps"]}
        self.assertNotIn("dangling_link", kinds)

    def test_a_failed_analysis_keeps_the_edits_pending(self):
        self.call("PATCH", self.url("/items/goals/Goal-1"), {"fields": {"plans": "New plan."}})
        with mock.patch("replay._ReplayModel.invoke", side_effect=RuntimeError("model down")):
            self.call("POST", self.url("/impact"))
            session = self.wait()
        self.assertEqual(session["impact_reports"], [])
        self.assertIsNone(session["changes"][0]["analyzed_in"])
        self.assertIn("model down", session["events"][-1]["detail"])


if __name__ == "__main__":
    unittest.main()
