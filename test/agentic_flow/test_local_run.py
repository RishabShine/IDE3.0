"""Run PRD-to-stakeholder extraction locally with a sample PRD and intent.

From the repository root, with Ollama running and the selected model installed:
    PYTHONPATH=src .venv/bin/python test/agentic_flow/test_local_run.py
    PYTHONPATH=src .venv/bin/python test/agentic_flow/test_local_run.py --example repairs

IDE3_MODEL selects the model through the existing application configuration.
This script makes a real model call only when run directly.
"""

import argparse
import json

from agentic_flow.user_modelling.graph import build_user_modelling


SAMPLE_PRD = """Library Group Study-Room Booking

McMaster students need to book library group study rooms themselves from their
phones. Today, students email the front desk to request a room. Front-desk staff
record requests in a shared spreadsheet and send confirmation emails manually.

Staff spend about six hours a week answering booking emails. Two staff members
can edit the spreadsheet at the same time and accidentally book the same room
twice. Students sometimes wait up to two days for a confirmation; some give up
and study somewhere else.

The application should let students see available rooms and make their own
bookings. A room must not be double booked, and students should receive booking
confirmation within one minute. The expected benefit for front-desk staff is
to spend less than one hour a week on booking emails. Students should arrive
knowing their room is reserved, without needing staff to arrange the booking.
"""

# Transcribed from the teammate's captured-intent output shared in the chat.
# This is example input only; no expected stakeholder list is supplied.
SAMPLE_INTENT = {
    "project_context": "",
    "single_statement_intent": (
        "Let McMaster students book library group study rooms themselves from their phone, "
        "so front-desk staff no longer spend hours a week handling bookings and rooms stop "
        "being double booked."
    ),
    "what": "book library group study rooms themselves from their phone",
    "how": "students book library group study rooms from their phone",
    "why": (
        "front-desk staff no longer spend hours a week handling bookings and rooms stop "
        "being double booked"
    ),
    "success_measure": (
        "front-desk staff no longer spend hours a week handling bookings and rooms stop "
        "being double booked"
    ),
    "current_process": (
        "Students email the front desk to request a group study room; staff manually "
        "record the request in a shared spreadsheet and then send an email reply "
        "confirming the booking, which can take up to two days."
    ),
    "problems": [
        {
            "id": "Problem-1",
            "description": "Staff spend about 6 hours a week answering booking emails.",
            "source": "Staff spend about 6 hours a week answering booking emails.",
        },
        {
            "id": "Problem-2",
            "description": (
                "Rooms get double booked because two staff edit the spreadsheet at the same "
                "time, so groups show up to a room that is already taken."
            ),
            "source": (
                "Rooms get double booked because two staff edit the spreadsheet at the same "
                "time, so groups show up to a room that is already taken."
            ),
        },
        {
            "id": "Problem-3",
            "description": (
                "Students wait up to two days for an email reply confirming their room, so "
                "they often give up and study somewhere else."
            ),
            "source": (
                "Students wait up to two days for an email reply confirming their room, so "
                "they often give up and study somewhere else."
            ),
        },
    ],
    "benefits": [
        {
            "id": "Benefit-1",
            "description": "Front-desk staff spend under 1 hour a week on booking emails.",
            "source": "Front-desk staff spend under 1 hour a week on booking emails.",
            "addresses": ["Problem-1"],
            "measure": "under 1 hour a week",
            "kind": "hard",
        },
        {
            "id": "Benefit-2",
            "description": (
                "Students never arrive at a room that is already taken, because no room is "
                "ever double booked."
            ),
            "source": (
                "Students never arrive at a room that is already taken, because no room is "
                "ever double booked."
            ),
            "addresses": ["Problem-2"],
            "measure": "no room is ever double booked",
            "kind": "hard",
        },
        {
            "id": "Benefit-3",
            "description": (
                "Students get their room confirmed within one minute of booking, so they "
                "no longer wait two days for a reply."
            ),
            "source": (
                "Students get their room confirmed within one minute of booking, so they "
                "no longer wait two days for a reply."
            ),
            "addresses": ["Problem-3"],
            "measure": "within one minute of booking",
            "kind": "hard",
        },
    ],
    "out_of_scope_problems": [],
}


REPAIRS_PRD = """Council Housing Repair Portal

Residents of council-owned flats report leaking taps, broken heaters, and other
maintenance problems by telephone. Repair coordinators copy the calls into a
spreadsheet and telephone field technicians to assign work. Residents cannot
see progress without calling again. Coordinators spend four hours each week
answering progress enquiries. Some jobs are assigned to two technicians because
the spreadsheet does not clearly show the current assignment.

The portal will let residents describe a fault and view its progress. Repair
coordinators will review reports and assign each job to one field technician.
Technicians will see their assigned jobs on a phone and record completion notes.
Each job must have at most one assigned technician. Coordinators should spend
less than one hour each week answering progress enquiries.

The council's finance staff provide the cost codes used for repair work and
receive monthly expenditure summaries. They will not operate the portal.
An existing accounting package stores expenditure records; the portal exports
a monthly CSV for that package. Buying replacement equipment and paying
contractors remain outside the portal's scope.
"""

# Synthetic intent for a second domain, using the teammate's output structure.
REPAIRS_INTENT = {
    "project_context": "Council-owned flats and their maintenance reporting process.",
    "single_statement_intent": (
        "Let residents report repairs and track progress while coordinators assign work "
        "to technicians, reducing progress enquiries and duplicate assignments."
    ),
    "what": "Report repairs, track progress, and assign repair work.",
    "how": "Residents and coordinators use the portal; technicians access jobs on a phone.",
    "why": "Reduce telephone progress enquiries and duplicate job assignments.",
    "success_measure": (
        "Less than one hour a week on progress enquiries, and at most one technician per job."
    ),
    "current_process": (
        "Residents telephone reports; coordinators record them in a spreadsheet and "
        "telephone technicians to assign work."
    ),
    "problems": [
        {
            "id": "Problem-1",
            "description": "Coordinators spend four hours each week answering progress enquiries.",
            "source": "Coordinators spend four hours each week answering progress enquiries.",
        },
        {
            "id": "Problem-2",
            "description": "Unclear spreadsheet assignments cause duplicate technician assignments.",
            "source": (
                "Some jobs are assigned to two technicians because the spreadsheet does "
                "not clearly show the current assignment."
            ),
        },
    ],
    "benefits": [
        {
            "id": "Benefit-1",
            "description": "Reduce time spent answering progress enquiries.",
            "source": (
                "Coordinators should spend less than one hour each week answering "
                "progress enquiries."
            ),
            "addresses": ["Problem-1"],
            "measure": "less than one hour each week",
            "kind": "hard",
        },
        {
            "id": "Benefit-2",
            "description": "Avoid duplicate technician assignments.",
            "source": "Each job must have at most one assigned technician.",
            "addresses": ["Problem-2"],
            "measure": "at most one assigned technician per job",
            "kind": "hard",
        },
    ],
    "scope_exclusions": ["Buying replacement equipment", "Paying contractors"],
    "out_of_scope_problems": [],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--example", choices=["library", "repairs"], default="library")
    args = parser.parse_args()
    prd, intent = (
        (REPAIRS_PRD, REPAIRS_INTENT)
        if args.example == "repairs"
        else (SAMPLE_PRD, SAMPLE_INTENT)
    )
    print("Example PRD:\n")
    print(prd)
    print("Extracting stakeholders using the sample captured intent...", flush=True)
    graph = build_user_modelling()
    result = graph.invoke({"prd": prd, "captured_intent": intent})
    print("\nExtracted stakeholders:\n")
    print(json.dumps(result["stakeholder_metadata"]["stakeholders"], indent=2))


if __name__ == "__main__":
    main()
