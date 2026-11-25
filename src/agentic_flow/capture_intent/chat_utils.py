"""Shared terminal loop for the capture-intent chat.py scripts.

Each script builds one graph and calls chat(). The graph waits for you to
paste a PRD, runs on it, and the derived intent is printed. Every model reply
is printed as it arrives (hide them with --quiet). Repeat as often as you like;
each PRD gets a fresh thread.
"""
import argparse
import json
import sys
import time
import uuid

from langchain_core.callbacks import BaseCallbackHandler
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agentic_flow.core.models import describe_model

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

Everyone signs in with their MacID. Equipment loans are outside the scope of
this project."""

END_MARKER = "END"


class PrintModelResponses(BaseCallbackHandler):
    """Print each model call's node and raw reply, so you can see what the model said
    before code checks it (IDs, PRD quotes, links and red flags are added afterwards)."""

    def __init__(self):
        self.started: dict = {}
        self.nodes: dict = {}

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, **kwargs):
        self.started[run_id] = time.monotonic()
        self.nodes[run_id] = (metadata or {}).get("langgraph_node", "model")
        print(f"\n[{self.nodes[run_id]}] calling the model...", flush=True)

    def on_llm_end(self, response, *, run_id, **kwargs):
        seconds = time.monotonic() - self.started.pop(run_id, time.monotonic())
        node = self.nodes.pop(run_id, "model")
        text = "".join(g.text for gen in response.generations for g in gen)
        try:
            text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
        except ValueError:
            pass
        print(f"[{node}] model response ({seconds:.1f}s):\n{text}", flush=True)

    def on_llm_error(self, error, *, run_id, **kwargs):
        node = self.nodes.pop(run_id, "model")
        self.started.pop(run_id, None)
        print(f"[{node}] model error: {type(error).__name__}: {error}", flush=True)


def _read_prd(prompt: str) -> str | None:
    """Read a pasted, multi-line PRD. Single blank lines (paragraph breaks) are kept.

    The paste ends at two blank lines in a row, a line with only END, or Ctrl-D.
    Pressing Enter before typing anything quits.
    """
    print(f"\n{prompt}\n\n(Paste it, then press Enter on two empty lines, "
          f"or type {END_MARKER}. Press Enter now to quit.)")
    lines: list[str] = []
    blank_run = 0
    while True:
        try:
            line = input("> " if not lines else "")
        except EOFError:
            break
        if line.strip() == END_MARKER:
            break
        if not line.strip():
            if not lines:
                return None
            blank_run += 1
            if blank_run == 2:
                break
        else:
            blank_run = 0
        lines.append(line)
    text = "\n".join(lines).strip()
    return text or None


def _items(items: list[dict], extra=None) -> str:
    if not items:
        return "  (none)"
    lines = []
    for item in items:
        line = f"  - {item['id']}: {item['description']}"
        if extra:
            line += extra(item)
        lines.append(line)
    return "\n".join(lines)


def _benefit(item: dict) -> str:
    fixes = ", ".join(item["addresses"]) or "none"
    return f"  [fixes {fixes}; {item['kind']}; measure: {item['measure'] or 'none'}]"


def show_intent(captured: dict) -> None:
    """Print whichever captured_intent sections the graph filled."""
    if "single_statement_intent" in captured:
        print(f"\nSSON ({captured.get('sson_source')}):\n  {captured['single_statement_intent']}")
        for key in ("what", "how", "why", "success_measure"):
            print(f"  {key}: {captured.get(key) or '(none)'}")
        print(f"G.1 context and objective:\n  {captured.get('context_and_objective') or '(none)'}")
    if "sson_evaluation" in captured:
        report = captured["sson_evaluation"]
        verdicts = ", ".join(f"{k}={v['verdict']}" for k, v in report["criteria"].items())
        print(f"SSON check: {report['score']}/100, "
              f"{'passed' if report['passed'] else 'needs work'}\n  {verdicts}")
        print(f"  feedback: {report['feedback']}")
    if "problems" in captured:
        print(f"\nG.2 current situation:\n  {captured.get('current_situation') or '(none)'}")
        print(f"Problems:\n{_items(captured['problems'])}")
    if "benefits" in captured:
        print(f"\nG.3 expected benefits:\n{_items(captured['benefits'], _benefit)}")
        print(f"  out of scope: {', '.join(captured.get('out_of_scope_problems') or []) or 'none'}")
    for key, title in (("effects", "E.5 effects"), ("invariants", "E.6 invariants"),
                       ("constraints", "Constraints"), ("scope_exclusions", "Scope exclusions")):
        if key in captured:
            print(f"\n{title}:\n{_items(captured[key])}")


def save_stakeholder_input(path: str, result: dict) -> None:
    """Write the state the stakeholders step reads: the PRD and the captured intent.

    Load it with json.load() and pass it to build_stakeholders().invoke(...).
    """
    state = {"prd": result.get("prd", ""), "captured_intent": result.get("captured_intent", {})}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(f"\nSaved the stakeholders input (prd + captured_intent) to {path}")


def chat(build_graph, title: str, description: str, asks_for_prd: bool = False) -> None:
    """Run `build_graph` on pasted PRDs until you quit.

    asks_for_prd=True: the graph starts with the PRD intake step, which pauses
    and asks for the PRD; your paste resumes it. Otherwise the PRD is read
    here first and passed in as state["prd"].
    """
    parser = argparse.ArgumentParser(description=f"{title}: {description}")
    parser.add_argument("--sample", action="store_true", help="run once on a sample PRD")
    parser.add_argument("--file", help="run once on a PRD read from this file")
    parser.add_argument("--json", action="store_true", help="also print the raw captured_intent")
    parser.add_argument("--quiet", action="store_true", help="do not print each model response")
    parser.add_argument("--out", metavar="FILE",
                        help="save {prd, captured_intent}: the stakeholders step's input")
    args = parser.parse_args()

    print(f"{title}\n{description}\nModel: {describe_model()}")

    graph = build_graph(InMemorySaver())
    once = bool(args.sample or args.file)

    def get_prd(prompt: str) -> str | None:
        if args.file:
            with open(args.file, encoding="utf-8") as f:
                return f.read()
        if args.sample:
            print(f"\nUsing the sample PRD:\n{SAMPLE_PRD}")
            return SAMPLE_PRD
        return _read_prd(prompt)

    while True:
        config = {"configurable": {"thread_id": f"chat-{uuid.uuid4()}"}}
        if not args.quiet:
            config["callbacks"] = [PrintModelResponses()]
        try:
            if asks_for_prd:
                result = graph.invoke({}, config)  # pauses at the PRD intake step
                while "__interrupt__" in result:
                    prd = get_prd(result["__interrupt__"][0].value["prompt_to_user"])
                    if not prd:
                        return
                    print("\n(thinking...)")
                    result = graph.invoke(Command(resume=prd), config)
            else:
                prd = get_prd("Paste your PRD.")
                if not prd:
                    return
                print("\n(thinking...)")
                result = graph.invoke({"prd": prd}, config)
        except Exception as error:  # show model/network errors, keep the chat going
            print(f"\nThe run failed: {type(error).__name__}: {error}", file=sys.stderr)
            if once:
                sys.exit(1)
            continue

        captured = result.get("captured_intent", {})
        print("\n" + "=" * 72 + "\nDerived intent (after code checks)")
        show_intent(captured)
        if args.json:
            print("\n" + json.dumps(captured, ensure_ascii=False, indent=2))
        if args.out:
            save_stakeholder_input(args.out, result)
        if once:
            return
