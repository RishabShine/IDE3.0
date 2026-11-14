from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import (
    START,
    END,
    StateGraph
)

from agentic_flow.state import AgentState
from agentic_flow.capture_intent.node import (
    capture_intent,
    evaluate_SSON,
)


def build_capture_intent():

    builder = StateGraph(AgentState)

    builder.add_node("capture_intent", capture_intent)

    builder.add_node("evaluate_SSON", evaluate_SSON)

    builder.add_edge(START, "capture_intent")

    builder.add_edge("capture_intent", "evaluate_SSON")

    builder.add_conditional_edges(
        "evaluate_SSON",
        lambda state: state["intent_metadata"]["evaluation_of_statement"],
        {
            "met": END,
            "partially_met": "capture_intent",
            "not_met": "capture_intent",
        }
    )

    return builder.compile(checkpointer=InMemorySaver())

capture_intent_graph = build_capture_intent()
# capture_intent_graph.get_graph(xray=True).draw_mermaid_png(
#     output_file_path="agentic_flow/capture_intent/capture_intent_graph.png"
# )
