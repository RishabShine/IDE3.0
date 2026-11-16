from langgraph.graph import (
    START,
    END,
    StateGraph
)

from agentic_flow.state import AgentState
from agentic_flow.capture_intent.sson.graph import build_capture_sson
from agentic_flow.capture_intent.context_expected_benefits_current_situation.graph import (
    build_capture_context,
)


def build_capture_intent(checkpointer=None):
    """SSON (G.1), then current situation (G.2) and expected benefits (G.3)."""

    builder = StateGraph(AgentState)

    # Both subgraphs inherit this graph's checkpointing and thread context.
    builder.add_node("capture_sson_graph", build_capture_sson())
    builder.add_node("capture_context_graph", build_capture_context())

    builder.add_edge(START, "capture_sson_graph")
    builder.add_edge("capture_sson_graph", "capture_context_graph")
    # "sson" at a read-back returns to the SSON; the context graph then resumes.
    builder.add_conditional_edges(
        "capture_context_graph",
        lambda state: state["context_metadata"]["choice"] == "sson",
        {True: "capture_sson_graph", False: END},
    )

    return builder.compile(checkpointer=checkpointer)

# capture_intent_graph = build_capture_intent()
# capture_intent_graph.get_graph(xray=True).draw_mermaid_png(
#     output_file_path="agentic_flow/capture_intent/capture_intent_graph.png"
# )
