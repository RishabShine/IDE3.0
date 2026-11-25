from langgraph.graph import END, START, StateGraph

from agentic_flow.capture_intent.context_expected_benefits_current_situation.node import (
    extract_current_situation,
    extract_environment,
    extract_expected_benefits,
)
from agentic_flow.state import AgentState


def build_capture_context(checkpointer=None):
    """G.2 problems, then G.3 benefits linked to them, then E.5/E.6. No user input."""
    builder = StateGraph(AgentState)
    builder.add_node("extract_current_situation", extract_current_situation)
    builder.add_node("extract_expected_benefits", extract_expected_benefits)
    builder.add_node("extract_environment", extract_environment)
    builder.add_edge(START, "extract_current_situation")
    builder.add_edge("extract_current_situation", "extract_expected_benefits")
    builder.add_edge("extract_expected_benefits", "extract_environment")
    builder.add_edge("extract_environment", END)
    return builder.compile(checkpointer=checkpointer)


# To redraw the diagram, from src/:
# build_capture_context().get_graph(xray=True).draw_mermaid_png(
#     output_file_path="agentic_flow/capture_intent/context_expected_benefits_current_situation/capture_context_graph.png"
# )
