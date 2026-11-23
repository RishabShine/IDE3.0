from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from agentic_flow.state import AgentState
from agentic_flow.user_modelling.stakeholders.node import (
    extract_stakeholders,
    prepare_stakeholder_request,
)


def build_user_modelling(checkpointer=None):
    """Extract the initial stakeholder list from a PRD without user interaction."""
    builder = StateGraph(AgentState)
    builder.add_node("prepare_stakeholder_request", prepare_stakeholder_request)
    builder.add_node("extract_stakeholders", extract_stakeholders)
    builder.add_edge(START, "prepare_stakeholder_request")
    builder.add_edge("prepare_stakeholder_request", "extract_stakeholders")
    builder.add_edge("extract_stakeholders", END)
    return builder.compile(checkpointer=checkpointer)


user_modelling_graph = build_user_modelling(checkpointer=InMemorySaver())
# user_modelling_graph.get_graph(xray=True).draw_mermaid_png(
#     output_file_path="agentic_flow/user_modelling/user_modelling_graph.png"
# )
