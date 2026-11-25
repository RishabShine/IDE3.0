"""Run Goal2Story in the terminal against a real Ollama model.

From the `src` directory, with Ollama running:

    python -m agentic_flow.goal2story.demo --prd       # PRD mode, sample PRD, no stops
    python -m agentic_flow.goal2story.demo --prd my_prd.txt --n 1
    python -m agentic_flow.goal2story.demo             # review mode: approve each level
    python -m agentic_flow.goal2story.demo --n 1       # smaller run: 1 × 1 × 1 = 1 story
    python -m agentic_flow.goal2story.demo --full      # whole IDE3.0 flow from the PRD

Set IDE3_MODEL to try another model, e.g. IDE3_MODEL=qwen2.5:7b.
"""
import argparse
import json
import uuid

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

SAMPLE_PRD = """Library Group Study-Room Booking

McMaster students need to book library group study rooms themselves from their
phones. Today, students email the front desk to request a room. Front-desk staff
record requests in a shared spreadsheet and send confirmation emails manually.

Staff spend about six hours a week answering booking emails. Two staff members
can edit the spreadsheet at the same time and accidentally book the same room
twice. Students sometimes wait up to two days for a confirmation.

The application should let students see available rooms and make their own
bookings. A room must not be double booked, and students should receive booking
confirmation within one minute. Front-desk staff should spend less than one hour
a week on booking emails.
"""

# Sample upstream output (lanes 1 and 2) for the study-room booking example.
SAMPLE_STATE = {
    "project_context": (
        "Mills Library has 20 group study rooms. Bookings are taken by email "
        "and at the front desk. Staff spend about 10 hours a week on bookings; "
        "double bookings and no-shows are common."
    ),
    "intent_metadata": {
        "single_statement_intent": (
            "Let McMaster students book library group study rooms themselves, "
            "so front-desk staff no longer handle bookings."
        ),
    },
    "captured_intent": {
        "goals": ["Cut library staff time spent on study-room bookings to under 1 hour per week."],
        "scope_exclusions": ["Equipment loans"],
        "constraints": ["Everyone signs in with their MacID."],
    },
    "stakeholder_metadata": {
        "stakeholders": [
            {"stakeholder_id": "Stakeholder-1", "name": "Students", "involvement": "direct",
             "summary": "McMaster students who book rooms for group work, often from their phones.",
             "justification": "They are the main users; their needs shape the booking flow."},
            {"stakeholder_id": "Stakeholder-2", "name": "Front-desk library staff", "involvement": "direct",
             "summary": "Handle study-room bookings and booking problems today.",
             "justification": "They know the booking rules and the manual work to remove."},
            {"stakeholder_id": "Stakeholder-3", "name": "Library IT", "involvement": "indirect",
             "summary": "Maintain library systems and MacID sign-in integration.",
             "justification": "They set integration and operational constraints."},
        ],
    },
}


def run(graph, state, n=None, prd=None):
    config = {"configurable": {"thread_id": f"demo-{uuid.uuid4()}"}}
    if n is not None:
        state = {**state, "goal2story_metadata": {"n_per_parent": n}}
    result = graph.invoke(state, config)
    while "__interrupt__" in result:
        print("\n" + "─" * 72)
        print(result["__interrupt__"][0].value["prompt_to_user"])
        if prd is not None:
            reply, prd = prd, None  # answer the PRD intake question
            print("\n> (PRD pasted)")
        else:
            reply = input("\n> ")
        print("(thinking…)")
        result = graph.invoke(Command(resume=reply), config)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--full", action="store_true",
                        help="run the whole IDE3.0 flow instead of the sample input")
    parser.add_argument("--n", type=int, default=None,
                        help="items per parent at each level (default 2)")
    parser.add_argument("--prd", nargs="?", const="", default=None, metavar="FILE",
                        help="PRD mode: read the PRD from FILE (default: a sample PRD)")
    parser.add_argument("--out", default=None, help="save the impact map as JSON")
    args = parser.parse_args()

    prd = None
    if args.prd is not None:
        prd = SAMPLE_PRD
        if args.prd:
            with open(args.prd, encoding="utf-8") as f:
                prd = f.read()

    if args.full:
        from agentic_flow.graph import build_ide3_chat
        result = run(build_ide3_chat(), {}, args.n, prd=prd)
    else:
        from agentic_flow.goal2story.graph import build_goal2story
        state = SAMPLE_STATE if prd is None else {**SAMPLE_STATE, "prd": prd}
        result = run(build_goal2story(InMemorySaver()), state, args.n)

    meta = result["goal2story_metadata"]
    output = {
        "goal": meta["goal"],
        "stories": [
            {k: s[k] for k in ("id", "text", "trace", "invest")}
            for s in meta["finalized_stories"]
        ],
        "open_questions": meta["open_questions"],
    }
    print("\n" + "═" * 72)
    print(json.dumps(output, ensure_ascii=False, indent=2))

    from agentic_flow.goal2story.artifacts import collect_goal2story
    nodes, edges = collect_goal2story(result)
    labels = {n["id"]: n["label"] for n in nodes}
    print("\nArtifact links:")
    for e in edges:
        print(f"  {e['source']} --{e['relation']}--> {e['target']}"
              f"  ({labels.get(e['target'], 'upstream')})")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"\nSaved the full impact map to {args.out}")


if __name__ == "__main__":
    main()
