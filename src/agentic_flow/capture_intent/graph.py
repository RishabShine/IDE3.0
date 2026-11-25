from langgraph.graph import END, START, StateGraph

from agentic_flow.capture_intent.context_expected_benefits_current_situation.graph import (
    build_capture_context,
)
from agentic_flow.capture_intent.sson.graph import build_capture_sson
from agentic_flow.state import AgentState


def build_capture_intent(checkpointer=None):
    """Derive state["captured_intent"] from the PRD, with no user input.

    SSON and G.1 first, since later steps judge relevance against the SSON;
    then G.2, G.3, E.5 and E.6.
    """
    builder = StateGraph(AgentState)
    # Both subgraphs inherit this graph's checkpointing and thread context.
    builder.add_node("capture_sson_graph", build_capture_sson())
    builder.add_node("capture_context_graph", build_capture_context())
    builder.add_edge(START, "capture_sson_graph")
    builder.add_edge("capture_sson_graph", "capture_context_graph")
    builder.add_edge("capture_context_graph", END)
    return builder.compile(checkpointer=checkpointer)


# To redraw the diagrams, from src/: python -m agentic_flow.draw_graphs
