"""Run Goal2Story in the terminal against a real Ollama model.

From the `src` directory, with Ollama running:

    python -m agentic_flow.goal2story.demo            # Goal2Story only, sample input
    python -m agentic_flow.goal2story.demo --n 1      # smaller run: 1 × 1 × 1 = 1 story
    python -m agentic_flow.goal2story.demo --full     # whole IDE3.0 flow from the SSON

Set IDE3_MODEL to try another model, e.g. IDE3_MODEL=qwen2.5:7b.
"""
import argparse
import json
import uuid

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

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
        "finalized_stakeholders": [
            {"stakeholder_id": 1, "name": "Students", "involvement": "direct",
             "summary": "McMaster students who book rooms for group work, often from their phones.",
             "justification": "They are the main users; their needs shape the booking flow."},
            {"stakeholder_id": 2, "name": "Front-desk library staff", "involvement": "direct",
             "summary": "Handle study-room bookings and booking problems today.",
             "justification": "They know the booking rules and the manual work to remove."},
            {"stakeholder_id": 3, "name": "Library IT", "involvement": "indirect",
             "summary": "Maintain library systems and MacID sign-in integration.",
             "justification": "They set integration and operational constraints."},
        ],
    },
}


def run(graph, state, n=None):
    config = {"configurable": {"thread_id": f"demo-{uuid.uuid4()}"}}
    if n is not None:
        state = {**state, "goal2story_metadata": {"n_per_parent": n}}
    result = graph.invoke(state, config)
    while "__interrupt__" in result:
        print("\n" + "─" * 72)
        print(result["__interrupt__"][0].value["prompt_to_user"])
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
    parser.add_argument("--out", default=None, help="save the approved stories as JSON")
    args = parser.parse_args()

    if args.full:
        from agentic_flow.graph import build_ide3_chat
        result = run(build_ide3_chat(), {}, args.n)
    else:
        from agentic_flow.goal2story.graph import build_goal2story
        result = run(build_goal2story(InMemorySaver()), SAMPLE_STATE, args.n)

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
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"\nSaved the full impact map to {args.out}")


if __name__ == "__main__":
    main()
