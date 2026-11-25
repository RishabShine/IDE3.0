"""Extension UI backend: the pipeline on recorded model responses (no model
calls) and the lifecycle actions the pages use."""
import tempfile
import time
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from agentic_flow.api.server import create_app
from agentic_flow.api.store import Store
from agentic_flow.state import RED_FLAG

import replay
from replay import SAMPLE_PRD


class ApiTests(unittest.TestCase):
    def setUp(self):
        models = replay.replay_models()
        models.__enter__()
        self.addCleanup(models.__exit__, None, None, None)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.client = TestClient(create_app(self.store))
        session = self.call("POST", "/api/sessions", {"prd": SAMPLE_PRD})
        self.sid = session["id"]
        self.wait()

    def call(self, method, path, body=None, status=200):
        response = self.client.request(method, path, json=body)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def url(self, suffix):
        return f"/api/sessions/{self.sid}{suffix}"

    def wait(self):
        for _ in range(200):
            session = self.call("GET", self.url(""))
            if not session["running"]:
                return session
            time.sleep(0.05)
        self.fail("pipeline did not finish")

    def stages(self, session):
        return {name: stage["status"] for name, stage in session["stages"].items()}

    def test_run_fills_every_page_and_registers_items_as_proposed(self):
        session = self.wait()
        self.assertEqual(set(self.stages(session).values()), {"done"})
        state = session["state"]
        self.assertEqual(len(state["captured_intent"]["problems"]), 4)
        self.assertEqual(len(state["stakeholder_metadata"]["stakeholders"]), 4)
        self.assertEqual(len(state["persona_metadata"]["personas"]), 3)
        self.assertTrue(state["captured_intent"]["single_statement_intent"].startswith(RED_FLAG))
        self.assertEqual(session["items"]["problems:Problem-1"]["status"], "proposed")
        self.assertEqual(session["items"]["singleton:sson"]["origin"], "ai")
        kinds = {gap["kind"] for gap in state["artifact_graph"]["gaps"]}
        self.assertIn("stakeholder_without_persona", kinds)
        nodes = [e["node"] for e in session["events"] if e["kind"] == "node"]
        self.assertEqual(nodes[0], "extract_sson")
        self.assertEqual(nodes[-1], "assemble_artifact_graph")

    def test_editing_the_sson_marks_everything_downstream_stale(self):
        session = self.call("PATCH", self.url("/singletons/sson"),
                            {"fields": {"single_statement_intent": "Book pickups online."}})
        self.assertEqual(self.stages(session), {
            "sson": "done", "sson_eval": "stale", "context": "stale",
            "stakeholders": "stale", "personas": "stale", "goals": "stale", "use_cases": "stale",
            "trace": "done"})
        meta = session["items"]["singleton:sson"]
        self.assertEqual(meta["status"], "edited")
        self.assertEqual(meta["history"][-1]["after"]["single_statement_intent"],
                         "Book pickups online.")
        self.assertTrue(meta["original"]["single_statement_intent"].startswith(RED_FLAG))

    def test_editing_a_stakeholder_only_stales_personas(self):
        session = self.call("PATCH", self.url("/items/stakeholders/Stakeholder-1"),
                            {"fields": {"summary": "Students who book slots."}})
        self.assertEqual(self.stages(session)["personas"], "stale")
        self.assertEqual(self.stages(session)["context"], "done")

    def test_add_checks_the_source_quote_and_numbers_after_the_last_id(self):
        error = self.call("POST", self.url("/items/problems"),
                          {"fields": {"description": "x", "source": "Not in the PRD."}}, 422)
        self.assertIn("not in the PRD", error["detail"])
        quote = "Volunteers track inventory on paper sheets taped to the shelves."
        session = self.call("POST", self.url("/items/problems"),
                            {"fields": {"description": "Inventory is on paper.", "source": quote}})
        added = session["state"]["captured_intent"]["problems"][-1]
        self.assertEqual((added["id"], added["source"]), ("Problem-5", quote))
        self.assertEqual(session["items"]["problems:Problem-5"]["status"], "added")

    def test_benefit_links_are_validated_and_measure_sets_kind(self):
        self.call("PATCH", self.url("/items/benefits/Benefit-4"),
                  {"fields": {"addresses": ["Problem-99"]}}, 422)
        session = self.call("PATCH", self.url("/items/benefits/Benefit-4"),
                            {"fields": {"addresses": ["Problem-4"], "measure": "two shifts"}})
        benefit = session["state"]["captured_intent"]["benefits"][3]
        self.assertEqual((benefit["addresses"], benefit["kind"]), (["Problem-4"], "hard"))
        kinds = {gap["kind"] for gap in session["state"]["artifact_graph"]["gaps"]}
        self.assertNotIn("unaddressed_problem", kinds)

    def test_delete_shows_a_dangling_link_and_restore_puts_it_back(self):
        session = self.call("DELETE", self.url("/items/problems/Problem-2"))
        self.assertEqual(session["items"]["problems:Problem-2"]["status"], "deleted")
        self.assertIn("dangling_link",
                      {gap["kind"] for gap in session["state"]["artifact_graph"]["gaps"]})
        session = self.call("POST", self.url("/items/problems/Problem-2/restore"))
        self.assertEqual(session["items"]["problems:Problem-2"]["status"], "proposed")
        self.assertNotIn("dangling_link",
                         {gap["kind"] for gap in session["state"]["artifact_graph"]["gaps"]})
        # a deleted ID is never reused
        self.call("DELETE", self.url("/items/problems/Problem-4"))
        session = self.call("POST", self.url("/items/problems"), {"fields": {"description": "New"}})
        self.assertEqual(session["state"]["captured_intent"]["problems"][-1]["id"], "Problem-5")

    def test_accept_all_accepts_only_proposed_items(self):
        self.call("PATCH", self.url("/items/effects/Effect-1"), {"fields": {"description": "More use."}})
        session = self.call("POST", self.url("/accept/effects"), {})
        self.assertEqual(session["items"]["effects:Effect-1"]["status"], "edited")
        session = self.call("POST", self.url("/accept/problems"), {})
        statuses = {k: m["status"] for k, m in session["items"].items() if k.startswith("problems:")}
        self.assertEqual(set(statuses.values()), {"accepted"})

    def test_rerun_with_downstream_replaces_output_and_keeps_the_old_one(self):
        self.call("PATCH", self.url("/singletons/sson"), {"fields": {"what": "book slots"}})
        self.call("PATCH", self.url("/items/problems/Problem-1"), {"fields": {"description": "Long lines."}})
        self.call("POST", self.url("/rerun"), {"stage": "context", "cascade": True})
        session = self.wait()
        self.assertEqual(self.stages(session)["sson_eval"], "stale")  # not part of this re-run
        for stage in ("context", "stakeholders", "personas"):
            self.assertEqual(self.stages(session)[stage], "done")
        self.assertEqual(session["items"]["problems:Problem-1"]["status"], "proposed")
        saved = session["snapshots"][0]["data"]["problems"]
        self.assertEqual(saved[0]["description"], "Long lines.")
        # the user's SSON edit survives a re-run of a later stage
        self.assertEqual(session["state"]["captured_intent"]["what"], "book slots")

    def test_rerun_of_one_stage_marks_its_downstream_stale(self):
        self.call("POST", self.url("/rerun"), {"stage": "stakeholders"})
        session = self.wait()
        self.assertEqual(self.stages(session)["personas"], "stale")
        session = self.call("POST", self.url("/stages/personas/keep"))
        self.assertEqual(self.stages(session)["personas"], "done")

    def test_edits_are_refused_while_running_and_sessions_persist(self):
        with mock.patch.object(replay, "DELAY_SECONDS", 0.5):
            self.call("POST", self.url("/rerun"), {"stage": "personas"})
            self.call("PATCH", self.url("/items/personas/Persona-1"), {"fields": {"name": "Sam"}}, 409)
            self.wait()
        reloaded = Store(self.tmp.name)
        self.assertEqual(reloaded.snapshot(self.sid)["state"]["prd"], SAMPLE_PRD)

    def test_goals_run_last_and_link_into_the_trace(self):
        session = self.wait()
        goals = session["state"]["goal_metadata"]["goals"]
        self.assertEqual(len(goals), 5)
        self.assertEqual(session["items"]["goals:Goal-1"]["status"], "proposed")
        edges = {(e["source"], e["relation"], e["target"])
                 for e in session["state"]["artifact_graph"]["edges"]}
        self.assertIn(("Goal-1", "delivers", "Benefit-1"), edges)
        self.assertIn(("Goal-1", "involves", "Stakeholder-2"), edges)
        nodes = [e["node"] for e in session["events"] if e["kind"] == "node"]
        self.assertEqual(nodes[-4:], ["extract_goals", "prepare_use_case_request",
                                      "extract_use_cases", "assemble_artifact_graph"])
        self.assertIn(("UC-1", "achieves", "Goal-1"), edges)
        self.assertEqual(session["state"]["use_case_metadata"]["issues"],
                         ["Goal-4 is achieved by no use case."])

    def test_goal_edits_validate_actors_links_and_resources(self):
        bad_actor = {"actors": [{"name": "Students", "stakeholder_id": "Stakeholder-99"}]}
        self.call("PATCH", self.url("/items/goals/Goal-4"), {"fields": bad_actor}, 422)
        self.call("PATCH", self.url("/items/goals/Goal-4"), {"fields": {"goal_type": "medium"}}, 422)
        self.call("PATCH", self.url("/items/goals/Goal-4"), {"fields": {"benefit_ids": ["Benefit-9"]}}, 422)
        session = self.call("PATCH", self.url("/items/goals/Goal-4"), {"fields": {
            "benefit_ids": ["Benefit-4"], "resources": "booking list\n\nbooking list\nreminders",
            "actors": [{"name": "Students", "stakeholder_id": "Stakeholder-1", "role": "User",
                        "involvement": "Pick up privately."}, {"name": "", "role": ""}],
        }})
        record = session["state"]["goal_metadata"]["goals"][3]
        self.assertEqual(record["resources"], ["booking list", "reminders"])
        self.assertEqual(len(record["actors"]), 1)  # the empty form row is dropped
        kinds = {(g["kind"], g["artifact_id"]) for g in session["state"]["artifact_graph"]["gaps"]}
        self.assertNotIn(("benefit_without_goal", "Benefit-4"), kinds)
        self.call("POST", self.url("/items/goals"), {"fields": {"statement": " "}}, 422)
        session = self.call("POST", self.url("/items/goals"), {"fields": {
            "statement": "Volunteers finish packing before opening.", "goal_type": "hard"}})
        self.assertEqual(session["state"]["goal_metadata"]["goals"][-1]["goal_id"], "Goal-6")

    def test_upstream_edits_mark_goals_stale(self):
        session = self.call("PATCH", self.url("/items/personas/Persona-1"),
                            {"fields": {"name": "Sam"}})
        self.assertEqual(self.stages(session)["goals"], "stale")
        self.call("POST", self.url("/rerun"), {"stage": "goals"})
        session = self.wait()
        self.assertEqual(self.stages(session)["goals"], "done")

    def test_sessions_saved_before_goals_get_a_pending_goals_stage(self):
        session = self.store.sessions[self.sid]
        del session["stages"]["goals"]
        self.store._save(session)
        self.assertEqual(Store(self.tmp.name).snapshot(self.sid)["stages"]["goals"]["status"],
                         "pending")

    def test_a_failing_stage_is_reported_and_the_session_stays_usable(self):
        with mock.patch("replay._ReplayModel.invoke",
                        side_effect=RuntimeError("model down")):
            self.call("POST", self.url("/rerun"), {"stage": "stakeholders", "cascade": True})
            session = self.wait()
        self.assertEqual(self.stages(session)["stakeholders"], "error")
        self.assertIn("model down", session["stages"]["stakeholders"]["error"])
        self.assertEqual(self.stages(session)["personas"], "stale")
        self.call("PATCH", self.url("/items/problems/Problem-1"), {"fields": {"description": "Ok."}})


if __name__ == "__main__":
    unittest.main()
