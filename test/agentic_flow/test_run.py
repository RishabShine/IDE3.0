"""The terminal runner (python -m agentic_flow.run / agentic_flow.graph), on recorded
model answers so it needs no model."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

import replay
from agentic_flow import run


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.prd = os.path.join(cls.tmp.name, "prd.txt")
        with open(cls.prd, "w", encoding="utf-8") as f:
            f.write(replay.SAMPLE_PRD)
        cls.saved = os.path.join(cls.tmp.name, "run.json")
        cls.models = replay.replay_models()
        cls.models.__enter__()
        cls.output, cls.state = cls.call(["--prd", cls.prd, "--out", cls.saved, "--quiet"], "main")

    @classmethod
    def tearDownClass(cls):
        cls.models.__exit__(None, None, None)
        cls.tmp.cleanup()

    @staticmethod
    def call(argv, default_step=None):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            state = run.main(argv, default_step=default_step)
        return buffer.getvalue(), state

    def test_main_graph_runs_the_whole_flow_and_saves_the_state(self):
        for heading in ("=== main", "capture_intent_graph / capture_sson_graph / extract_sson", "use_case_graph / extract_use_cases",
                        "Use case model: Food Bank Pickup Scheduler", "Trace: "):
            self.assertIn(heading, self.output)
        with open(self.saved, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["use_case_metadata"]["use_cases"][0]["name"], "Book pickup slot")

    def test_main_graph_asks_for_the_prd_first_when_none_is_given(self):
        lines = [*replay.SAMPLE_PRD.strip().splitlines(), "END"]
        with mock.patch("builtins.input", side_effect=lines):
            output, state = self.call(["--quiet"], "main")
        self.assertIn("Paste your PRD", output)
        self.assertTrue(state["prd"].startswith("Campus Food Bank Pickup Scheduler"))
        self.assertIn("artifact_graph", state)

    def test_a_graph_runs_the_steps_it_needs_first(self):
        output, state = self.call(["goals", "--prd", self.prd, "--quiet"])
        order = [output.index(f"=== {s}:") for s in ("sson", "context", "stakeholders", "personas", "goals")]
        self.assertEqual(order, sorted(order))
        self.assertNotIn("=== use_cases", output)
        self.assertEqual(len(state["goal_metadata"]["goals"]), 5)

    def test_every_graph_runs_alone_on_a_saved_state(self):
        for step in ("sson", "context", "capture_intent", "stakeholders", "personas",
                     "user_modelling", "goals", "use_cases", "artifact_graph", "goal2story"):
            with self.subTest(step=step):
                output, _ = self.call([step, "--state", self.saved, "--only", "--quiet"])
                self.assertEqual(output.count("=== ") , 2, output)  # its start and finish only

    def test_impact_from_an_edit_and_from_a_delete(self):
        output, state = self.call(["impact", "--state", self.saved, "--quiet", "--edit",
                                   "problems:Problem-2", "description=About 20 kg is thrown out weekly."])
        self.assertIn("Change: edited problems:Problem-2", output)
        self.assertIn("Benefit-2", [c["id"] for c in state["impact_report"]["candidates"]])
        output, state = self.call(["impact", "--state", self.saved, "--quiet",
                                   "--delete", "benefits:Benefit-1"])
        self.assertIn("unlink", output)
        with self.assertRaises(SystemExit):
            self.call(["impact", "--state", self.saved, "--quiet", "--delete", "benefits:Benefit-9"])


if __name__ == "__main__":
    unittest.main()
