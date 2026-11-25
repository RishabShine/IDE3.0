from langgraph.graph import END, START, StateGraph

from agentic_flow.capture_intent.sson.node import evaluate_sson, extract_sson
from agentic_flow.state import AgentState


def build_capture_sson(checkpointer=None):
    """SSON and G.1 from the PRD, then a non-blocking quality check. No user input."""
    builder = StateGraph(AgentState)
    builder.add_node("extract_sson", extract_sson)
    builder.add_node("evaluate_sson", evaluate_sson)
    builder.add_edge(START, "extract_sson")
    builder.add_edge("extract_sson", "evaluate_sson")
    builder.add_edge("evaluate_sson", END)
    return builder.compile(checkpointer=checkpointer)


# To redraw the diagram, from src/:
# build_capture_sson().get_graph(xray=True).draw_mermaid_png(
#     output_file_path="agentic_flow/capture_intent/sson/capture_sson_graph.png"
# )
