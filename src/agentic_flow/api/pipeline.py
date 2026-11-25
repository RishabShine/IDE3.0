"""The PRD-to-artifacts pipeline the UI drives, built from the existing graphs.

First run: capture_intent -> user_modelling -> goals -> use cases -> artifact
graph, the same composed LangGraph as the main graph. Re-runs: one stage at a time, each a compiled graph of its own, so
editing the SSON can re-run only what depends on it.
"""
from typing import Callable, Iterable

from langgraph.graph import END, START, StateGraph

from agentic_flow.artifact_graph.graph import build_artifact_graph_step
from agentic_flow.capture_intent.context_expected_benefits_current_situation.graph import (
    build_capture_context,
)
from agentic_flow.capture_intent.graph import build_capture_intent
from agentic_flow.capture_intent.sson.node import evaluate_sson, extract_sson
from agentic_flow.goals.graph import build_goals
from agentic_flow.state import AgentState
from agentic_flow.user_modelling.graph import build_user_modelling
from agentic_flow.user_modelling.personas.graph import build_personas
from agentic_flow.user_modelling.stakeholders.graph import build_stakeholders
from agentic_flow.use_cases.graph import build_use_cases

# Upstream to downstream. "trace" needs no model and is rebuilt after every change.
STAGES = ["sson", "sson_eval", "context", "stakeholders", "personas", "goals", "use_cases", "trace"]
MODEL_STAGES = STAGES[:-1]

STAGE_LABELS = {
    "sson": "Extract SSON and G.1",
    "sson_eval": "Evaluate SSON",
    "context": "Situation, benefits, environment",
    "stakeholders": "Extract stakeholders",
    "personas": "Extract personas",
    "goals": "Extract goals",
    "use_cases": "Build use case model",
    "trace": "Assemble artifact graph",
}

# What becomes out of date when a stage's output changes (by edit or re-run).
# Goals read the intent and user model; the use case model reads all of them.
DOWNSTREAM = {
    "sson": ["sson_eval", "context", "stakeholders", "personas", "goals", "use_cases"],
    "sson_eval": [],
    "context": ["stakeholders", "personas", "goals", "use_cases"],
    "stakeholders": ["personas", "goals", "use_cases"],
    "personas": ["goals", "use_cases"],
    "goals": ["use_cases"],
    "use_cases": [],
}

NODE_STAGE = {
    "extract_sson": "sson",
    "evaluate_sson": "sson_eval",
    "extract_current_situation": "context",
    "extract_expected_benefits": "context",
    "extract_environment": "context",
    "prepare_stakeholder_request": "stakeholders",
    "extract_stakeholders": "stakeholders",
    "prepare_persona_request": "personas",
    "extract_personas": "personas",
    "prepare_goal_request": "goals",
    "extract_goals": "goals",
    "prepare_use_case_request": "use_cases",
    "extract_use_cases": "use_cases",
    "assemble_artifact_graph": "trace",
}
LAST_NODE = {
    "sson": "extract_sson",
    "sson_eval": "evaluate_sson",
    "context": "extract_environment",
    "stakeholders": "extract_stakeholders",
    "personas": "extract_personas",
    "goals": "extract_goals",
    "use_cases": "extract_use_cases",
    "trace": "assemble_artifact_graph",
}


def build_pipeline():
    builder = StateGraph(AgentState)
    builder.add_node("capture_intent_graph", build_capture_intent())
    builder.add_node("user_modelling_graph", build_user_modelling())
    builder.add_node("goals_graph", build_goals())
    builder.add_node("use_case_graph", build_use_cases())
    builder.add_node("artifact_graph_step", build_artifact_graph_step())
    builder.add_edge(START, "capture_intent_graph")
    builder.add_edge("capture_intent_graph", "user_modelling_graph")
    builder.add_edge("user_modelling_graph", "goals_graph")
    builder.add_edge("goals_graph", "use_case_graph")
    builder.add_edge("use_case_graph", "artifact_graph_step")
    builder.add_edge("artifact_graph_step", END)
    return builder.compile()


def _single_node(name: str, fn: Callable):
    builder = StateGraph(AgentState)
    builder.add_node(name, fn)
    builder.add_edge(START, name)
    builder.add_edge(name, END)
    return builder.compile()


STAGE_GRAPHS: dict[str, Callable] = {
    "sson": lambda: _single_node("extract_sson", extract_sson),
    "sson_eval": lambda: _single_node("evaluate_sson", evaluate_sson),
    "context": build_capture_context,
    "stakeholders": build_stakeholders,
    "personas": build_personas,
    "goals": build_goals,
    "use_cases": build_use_cases,
    "trace": build_artifact_graph_step,
}

STATE_KEYS = set(AgentState.__annotations__)

OnUpdate = Callable[[dict], None]
OnNode = Callable[[str], None]


def _stream(graph, state: dict, on_update: OnUpdate, on_node: OnNode) -> None:
    """Run a graph, handing every state update and finished node to the callbacks."""
    for _namespace, update in graph.stream(state, stream_mode="updates", subgraphs=True):
        for node, values in update.items():
            if isinstance(values, dict):
                changes = {k: v for k, v in values.items() if k in STATE_KEYS}
                if changes:
                    on_update(changes)
            if node in NODE_STAGE:
                on_node(node)


def run_full(state: dict, on_update: OnUpdate, on_node: OnNode) -> None:
    _stream(build_pipeline(), state, on_update, on_node)


def run_stages(stages: Iterable[str], get_state: Callable[[], dict],
               on_update: OnUpdate, on_node: OnNode) -> None:
    """Run the given stages in order, each on the state the previous one left."""
    for stage in stages:
        _stream(STAGE_GRAPHS[stage](), get_state(), on_update, on_node)
