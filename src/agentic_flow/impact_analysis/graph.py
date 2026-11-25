from langgraph.graph import END, START, StateGraph

from agentic_flow.impact_analysis.node import (
    assess_impact,
    collect_candidates,
    validate_proposals,
)
from agentic_flow.state import AgentState


def build_impact_analysis(checkpointer=None):
    """Assess what the edits in state["impact_request"] mean for linked artifacts.

    collect candidates (trace links, no model) -> assess (one model call)
    -> validate proposals (code). Writes state["impact_report"]; applies nothing.
    """
    builder = StateGraph(AgentState)
    builder.add_node("collect_candidates", collect_candidates)
    builder.add_node("assess_impact", assess_impact)
    builder.add_node("validate_proposals", validate_proposals)
    builder.add_edge(START, "collect_candidates")
    builder.add_edge("collect_candidates", "assess_impact")
    builder.add_edge("assess_impact", "validate_proposals")
    builder.add_edge("validate_proposals", END)
    return builder.compile(checkpointer=checkpointer)
