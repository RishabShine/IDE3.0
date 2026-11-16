from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import (
    START,
    END,
    StateGraph
)

from agentic_flow.state import AgentState
from agentic_flow.capture_intent.sson.node import (
    capture_sson,
    evaluate_sson,
)


def build_capture_sson(checkpointer=None):

    builder = StateGraph(AgentState)

    builder.add_node("capture_sson", capture_sson)

    builder.add_node("evaluate_sson", evaluate_sson)

    builder.add_edge(START, "capture_sson")

    builder.add_edge("capture_sson", "evaluate_sson")

    builder.add_conditional_edges(
        "evaluate_sson",
        lambda state: state["intent_metadata"]["passed"],
        {True: END, False: "capture_sson"},
    )

    return builder.compile(checkpointer=checkpointer)

# Standalone use keeps its own memory; embedded use inherits the parent's.
capture_sson_graph = build_capture_sson(checkpointer=InMemorySaver())
# capture_sson_graph.get_graph(xray=True).draw_mermaid_png(
#     output_file_path="agentic_flow/capture_intent/sson/capture_sson_graph.png"
# )
