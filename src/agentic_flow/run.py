"""Run the IDE3.0 flow, or any one of its graphs, from the terminal.

Every run makes real model calls to the model chosen in IDE3.0/.env (see
agentic_flow/core/models.py). Each model reply is printed as it arrives; hide
them with --quiet.

From src/:

    python -m agentic_flow.graph                                   # whole flow, paste a PRD
    python -m agentic_flow.run main --prd food_bank_prd.txt --out run.json
    python -m agentic_flow.run goals --prd food_bank_prd.txt       # runs what goals needs first
    python -m agentic_flow.run goals --state run.json --only       # only goals, on a saved run

Input: --prd FILE, or --state FILE (a JSON state saved with --out). With neither,
you are asked to paste a PRD. Given a PRD, any earlier step the chosen graph
needs is run first; --only skips that and runs just the chosen graph.
"""
import argparse
import json
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agentic_flow.capture_intent.chat_utils import PrintModelResponses, _read_prd, show_intent
from agentic_flow.core.models import describe_model


def _intent(s): return s.get("captured_intent") or {}


@dataclass(frozen=True)
class Step:
    build: Callable  # () -> builder function taking a checkpointer
    about: str
    needs: tuple[str, ...]  # earlier steps, in order
    done: Callable[[dict], bool]  # is this step's output already in the state?


def _builder(module: str, name: str) -> Callable:
    def load():
        return getattr(__import__(module, fromlist=[name]), name)
    return load


STEPS: dict[str, Step] = {
    "sson": Step(_builder("agentic_flow.capture_intent.sson.graph", "build_capture_sson"),
                 "SSON and G.1, then the L04 evaluation", (),
                 lambda s: bool(_intent(s).get("single_statement_intent"))),
    "context": Step(_builder("agentic_flow.capture_intent.context_expected_benefits_current_situation.graph",
                             "build_capture_context"),
                    "G.2 situation and problems, G.3 benefits, E.5/E.6 environment", ("sson",),
                    lambda s: "problems" in _intent(s)),
    "capture_intent": Step(_builder("agentic_flow.capture_intent.graph", "build_capture_intent"),
                           "sson, then context", (), lambda s: "problems" in _intent(s)),
    "stakeholders": Step(_builder("agentic_flow.user_modelling.stakeholders.graph", "build_stakeholders"),
                         "stakeholders from the PRD and intent", ("sson", "context"),
                         lambda s: bool(s.get("stakeholder_metadata"))),
    "personas": Step(_builder("agentic_flow.user_modelling.personas.graph", "build_personas"),
                     "personas linked to stakeholders", ("sson", "context", "stakeholders"),
                     lambda s: bool(s.get("persona_metadata"))),
    "user_modelling": Step(_builder("agentic_flow.user_modelling.graph", "build_user_modelling"),
                           "stakeholders, then personas", ("sson", "context"),
                           lambda s: bool(s.get("persona_metadata"))),
    "goals": Step(_builder("agentic_flow.goals.graph", "build_goals"),
                  "hard/soft goals linked to benefits and stakeholders",
                  ("sson", "context", "stakeholders", "personas"),
                  lambda s: bool(s.get("goal_metadata"))),
    "use_cases": Step(_builder("agentic_flow.use_cases.graph", "build_use_cases"),
                      "rough L13 use case model", ("sson", "context", "stakeholders", "personas", "goals"),
                      lambda s: bool(s.get("use_case_metadata"))),
    "artifact_graph": Step(_builder("agentic_flow.artifact_graph.graph", "build_artifact_graph_step"),
                           "trace links and gaps (no model)",
                           ("sson", "context", "stakeholders", "personas", "goals", "use_cases"),
                           lambda s: bool(s.get("artifact_graph"))),
    "goal2story": Step(_builder("agentic_flow.goal2story.graph", "build_goal2story"),
                       "user stories per goal (outside the main flow)",
                       ("sson", "context", "stakeholders", "personas", "goals"),
                       lambda s: bool(s.get("goal2story_metadata"))),
    "impact": Step(_builder("agentic_flow.impact_analysis.graph", "build_impact_analysis"),
                   "impact analysis of an --edit or --delete",
                   ("sson", "context", "stakeholders", "personas", "goals", "use_cases"),
                   lambda s: bool(s.get("impact_report"))),
    "main": Step(_builder("agentic_flow.graph", "build_ide3_chat"),
                 "the whole flow: intent, user modelling, goals, use cases, trace", (),
                 lambda s: bool(s.get("artifact_graph"))),
}


# running a graph
# -----------------------------------------------------------------------------

def run_graph(name: str, state: dict, quiet: bool = False) -> dict:
    """Run one graph to the end, answering any review question from the keyboard."""
    graph = STEPS[name].build()(InMemorySaver())
    config = {"configurable": {"thread_id": f"run-{uuid.uuid4()}"}}
    if not quiet:
        config["callbacks"] = [PrintModelResponses()]
    print(f"\n=== {name}: {STEPS[name].about}", flush=True)
    started = time.monotonic()
    payload = state
    while True:
        for namespace, update in graph.stream(payload, config, stream_mode="updates", subgraphs=True):
            for node in update:
                if not node.startswith("__"):
                    where = " / ".join(n.split(":")[0] for n in namespace)
                    print(f"  ✓ {where + ' / ' if where else ''}{node}", flush=True)
        snapshot = graph.get_state(config)
        if not snapshot.next:
            break
        # only goal2story's review mode asks questions (when there is no PRD)
        question = snapshot.interrupts[0].value.get("prompt_to_user", "")
        print(f"\n{question}")
        payload = Command(resume=input("\n> "))
    print(f"=== {name} finished in {time.monotonic() - started:.1f}s", flush=True)
    return snapshot.values


def run_with_upstream(name: str, state: dict, only: bool, quiet: bool) -> dict:
    if not only:
        for needed in STEPS[name].needs:
            if not STEPS[needed].done(state):
                state = run_graph(needed, state, quiet)
    return run_graph(name, state, quiet)


# impact analysis input
# -----------------------------------------------------------------------------

def make_change(state: dict, edit: list[str] | None, delete: str | None) -> dict:
    """Apply one --edit KEY FIELD=VALUE or --delete KEY to the state and describe it."""
    import copy

    from agentic_flow.impact_analysis.node import COLLECTIONS, artifact_id_of, index_artifacts

    key = edit[0] if edit else delete
    artifacts = index_artifacts(state)
    entry = artifacts.get(artifact_id_of(key))
    if entry is None or entry["key"] != key:
        known = ", ".join(sorted(e["key"] for e in artifacts.values())[:12])
        raise SystemExit(f"No artifact {key}. Keys look like: {known}, ...")
    before = copy.deepcopy(entry["record"])
    if delete:
        parent, list_key = COLLECTIONS[entry["collection"]][:2]
        state[parent][list_key] = [r for r in state[parent][list_key] if r is not entry["record"]]
        return {"key": key, "action": "deleted", "before": before, "after": None}
    field, _, value = edit[1].partition("=")
    if field not in entry["fields"]:
        raise SystemExit(f"{key} has no revisable field {field!r}; try one of {list(entry['fields'])}.")
    entry["record"][field] = value
    return {"key": key, "action": "edited", "before": before, "after": copy.deepcopy(entry["record"])}


# output
# -----------------------------------------------------------------------------

def _line(prefix: str, text: str) -> None:
    print(f"  {prefix:<15} {text}")


def summarize(state: dict) -> None:
    if _intent(state):
        show_intent(_intent(state))
    for title, records, key, text in (
        ("Stakeholders", (state.get("stakeholder_metadata") or {}).get("stakeholders"),
         "stakeholder_id", lambda r: f"{r['name']} ({r.get('involvement') or '?'})"),
        ("Personas", (state.get("persona_metadata") or {}).get("personas"),
         "persona_id", lambda r: f"{r.get('name') or r.get('role')} -> {r.get('stakeholder_id')}"),
        ("Goals", (state.get("goal_metadata") or {}).get("goals"),
         "goal_id", lambda r: f"[{r.get('goal_type') or '?'}] {r['statement']} -> {', '.join(r.get('benefit_ids') or []) or 'no benefit'}"),
    ):
        if records is not None:
            print(f"\n{title} ({len(records)})")
            for r in records:
                _line(r[key], text(r))
    model = state.get("use_case_metadata")
    if model:
        actors = {a["actor_id"]: a["name"] for a in model["actors"]}
        print(f"\nUse case model: {model['system_name']} ({len(model['use_cases'])} use cases)")
        for c in model["use_cases"]:
            _line(c["use_case_id"], f"{c['name']}  [{actors.get(c['primary_actor_id'], '?')}] -> {', '.join(c['goal_ids']) or 'no goal'}")
        for r in model["relationships"]:
            _line(f"«{r['kind']}»", f"{r['source']} -> {r['target']} {r['condition']}".strip())
        for issue in model["issues"]:
            _line("check", issue)
    stories = (state.get("goal2story_metadata") or {}).get("finalized_stories")
    if stories:
        print(f"\nUser stories ({len(stories)})")
        for s in stories:
            _line(s["id"], f"{s['text']} ({s['parent_id']})")
    graph = state.get("artifact_graph")
    if graph:
        print(f"\nTrace: {len(graph['nodes'])} artifacts, {len(graph['edges'])} links, {len(graph['gaps'])} gaps")
        for gap in graph["gaps"]:
            _line(gap["kind"], gap["detail"])
    report = state.get("impact_report")
    if report:
        print(f"\nImpact: {len(report['candidates'])} linked artifacts checked")
        for p in report["proposals"]:
            _line(f"{p['proposal_id']} {p['kind']}", f"{p['artifact_id'] or p['label']}: {p['reason']} {p['fields'] or ''}")
        for u in report["unaffected"]:
            _line("unaffected", f"{u['artifact_id']}: {u['reason']}")
        for note in report["notes"]:
            _line("note", note)


# command line
# -----------------------------------------------------------------------------

def main(argv: list[str] | None = None, default_step: str | None = None) -> dict:
    parser = argparse.ArgumentParser(
        description="Run the IDE3.0 flow or one of its graphs, with real model calls.",
        epilog="Graphs: " + "; ".join(f"{n}: {s.about}" for n, s in STEPS.items()))
    if default_step is None:
        parser.add_argument("step", choices=list(STEPS), help="which graph to run")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--prd", metavar="FILE", help="read the PRD from FILE")
    source.add_argument("--state", metavar="FILE", help="start from a state saved with --out")
    parser.add_argument("--only", action="store_true", help="do not run earlier steps first")
    parser.add_argument("--out", metavar="FILE", help="save the final state as JSON")
    parser.add_argument("--json", action="store_true", help="print the final state as JSON")
    parser.add_argument("--quiet", action="store_true", help="do not print each model reply")
    parser.add_argument("--edit", nargs=2, metavar=("KEY", "FIELD=VALUE"),
                        help="impact: edit an artifact first, e.g. problems:Problem-2 description=...")
    parser.add_argument("--delete", metavar="KEY", help="impact: delete an artifact first")
    args = parser.parse_args(argv)
    step = default_step or args.step

    print(f"IDE3.0 · {step} · model: {describe_model()}")
    if args.state:
        with open(args.state, encoding="utf-8") as f:
            state = json.load(f)
    elif args.prd:
        with open(args.prd, encoding="utf-8") as f:
            state = {"prd": f.read()}
    else:
        prd = _read_prd("Paste your PRD. The flow starts from it.")
        if not prd:
            sys.exit(0)
        state = {"prd": prd}
    if not (state.get("prd") or "").strip():
        sys.exit("A PRD is required: pass --prd FILE, or a --state that contains one.")

    if step == "impact":
        if not (args.edit or args.delete):
            sys.exit("impact needs --edit KEY FIELD=VALUE or --delete KEY.")
        if not args.only:
            for needed in STEPS["impact"].needs:
                if not STEPS[needed].done(state):
                    state = run_graph(needed, state, args.quiet)
        change = make_change(state, args.edit, args.delete)
        print(f"\nChange: {change['action']} {change['key']}")
        state = run_graph("impact", {**state, "impact_request": {"changes": [change]}}, args.quiet)
    else:
        state = run_with_upstream(step, state, args.only, args.quiet)

    print("\n" + "=" * 72)
    summarize(state)
    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        print(f"\nSaved the state to {args.out} (use it with --state).")
    return state


if __name__ == "__main__":
    main()
