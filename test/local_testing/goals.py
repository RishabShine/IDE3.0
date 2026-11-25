"""Run user modelling followed by goal extraction against real local models.

From the repository root, with Ollama running:
    PYTHONPATH=src IDE3_MODEL=qwen2.5:7b .venv/bin/python test/local_testing/goals.py --example repairs
    PYTHONPATH=src IDE3_MODEL=qwen2.5:7b .venv/bin/python test/local_testing/goals.py --example sparse

Sample data is used only when this file is run directly. Expected results are
described in comments for manual review, not passed to the extraction models.
Goal2Story is not invoked.
"""

import argparse
import json

from agentic_flow.goals.graph import build_goals
from agentic_flow.user_modelling.graph import build_user_modelling
from user_modelling.stakeholders import REPAIRS_INTENT, REPAIRS_PRD


GOALS_REPAIRS_PRD = REPAIRS_PRD + """
Project objectives and agreed approaches:

The council wants repair coordinators to spend less than one hour per week on
progress enquiries, down from the current four hours. Coordinators want to
spend that time arranging repairs instead. Residents want to find out what is
happening without another telephone call. The agreed approach is for technicians
to record completion notes, coordinators to keep the repair-status records
current, and residents to consult those records through the portal.

Coordinators and field technicians want to avoid duplicate job assignments,
so two technicians are not sent to the same job unnecessarily. The assignment
subsystem supports this objective by checking the current job-assignment record
when a coordinator assigns a technician, and refusing a second assignment while
the first is active. The coordinator chooses the technician; the subsystem
performs the check. These are the agreed actions, not additional project goals.

Residents also want the repair process to feel reassuring and easy to understand.
The team has not agreed on a measurement, a target, or an approach for this
quality objective. Asha's concerns about uncertain repair progress are one
reason this objective matters.

Finance staff want each monthly expenditure summary to match the recorded costs
of completed repairs, so they can account for repair spending. They supply cost
codes, and the portal exports the completed-repair cost records as a monthly CSV
for the existing accounting package.

The decision to use CSV is an integration constraint. It is not a separate
business objective to create a new file format or replace the accounting package.
"""

# Use the existing synthetic intent snapshot. The additional detail remains in
# the PRD; no expected goal list or precomputed actors are supplied to the model.
GOALS_REPAIRS_INTENT = REPAIRS_INTENT

# Manual checks: preserve the enquiry target and duplicate-assignment objective;
# recognise the reassuring/easy-to-understand objective as soft without inventing
# a metric or plan; retain the assignment subsystem actor with a null stakeholder
# link; use actual extracted stakeholder IDs for supported human actor links.
# Also retain supported goals from the original persona notes, including Morgan's
# desired outcome even when Morgan's stakeholder relationship remains unresolved.

SPARSE_PRD = """Neighbourhood History Archive

The project's objective is for exploring the archive to feel pleasant and
welcoming. No satisfaction measure, target, or implementation approach has
been agreed. The document does not identify who will carry out work to achieve
this objective or which resources will be used.

The prototype must be implemented in Python. This is an imposed technical
constraint, not an additional objective of the project.
"""

SPARSE_INTENT = {
    "single_statement_intent": "Make exploring the neighbourhood history archive pleasant and welcoming.",
    "problems": [],
    "benefits": [],
}

# Manual checks: retain the supplied soft objective; leave unspecified actors,
# resources, plans, and rationale empty. Do not invent a target or decompose
# "pleasant and welcoming" into newly designed goals. Python is a constraint.


def run(prd, intent):
    state = build_user_modelling().invoke({"prd": prd, "captured_intent": intent})
    print("\nExtracted stakeholders:\n")
    print(json.dumps(state["stakeholder_metadata"]["stakeholders"], indent=2))
    print("\nExtracted personas:\n")
    print(json.dumps(state["persona_metadata"]["personas"], indent=2))

    result = build_goals().invoke(state)
    print("\nExtracted goals:\n")
    print(json.dumps(result["goal_metadata"]["goals"], indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--example", choices=["repairs", "sparse"], default="repairs")
    args = parser.parse_args()
    if args.example == "repairs":
        run(GOALS_REPAIRS_PRD, GOALS_REPAIRS_INTENT)
    else:
        run(SPARSE_PRD, SPARSE_INTENT)


if __name__ == "__main__":
    main()
