from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from agentic_flow.capture_intent.node import extract_intent, prepare_intent_request
from agentic_flow.state import AgentState


def build_capture_intent(checkpointer=None):
    """Derive intent artifacts from the PRD in one pass without user interaction."""
    builder = StateGraph(AgentState)
    builder.add_node("prepare_intent_request", prepare_intent_request)
    builder.add_node("extract_intent", extract_intent)
    builder.add_edge(START, "prepare_intent_request")
    builder.add_edge("prepare_intent_request", "extract_intent")
    builder.add_edge("extract_intent", END)
    return builder.compile(checkpointer=checkpointer)


# Standalone use keeps its own memory; embedded use inherits the parent's.
capture_intent_graph = build_capture_intent(checkpointer=InMemorySaver())
# capture_intent_graph.get_graph(xray=True).draw_mermaid_png(
#     output_file_path="agentic_flow/capture_intent/capture_intent_graph.png"
# )
