from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import (
    START,
    END,
    StateGraph
)

from agentic_flow.state import AgentState
from agentic_flow.capture_intent.context_expected_benefits_current_situation.node import (
    capture_current_situation,
    evaluate_current_situation,
    confirm_current_situation,
    capture_expected_benefits,
    evaluate_expected_benefits,
    confirm_expected_benefits,
    benefits_basis,
)


def build_capture_context(checkpointer=None):
    """
    Current situation (G.2), then expected benefits (G.3). Each stage loops
    capture -> evaluate until the evaluator passes (or the tries run out), then
    the user answers the read-back: yes (next step), no (change this list), or
    the name of an earlier step to revise ("problems", "sson").

    "sson" ends this graph; the parent runs the SSON graph and comes back here.
    Whatever was graded against something that has since changed is graded again
    before its read-back is shown.
    """

    builder = StateGraph(AgentState)

    builder.add_node("capture_current_situation", capture_current_situation)
    builder.add_node("evaluate_current_situation", evaluate_current_situation)
    builder.add_node("confirm_current_situation", confirm_current_situation)
    builder.add_node("capture_expected_benefits", capture_expected_benefits)
    builder.add_node("evaluate_expected_benefits", evaluate_expected_benefits)
    builder.add_node("confirm_expected_benefits", confirm_expected_benefits)

    def problems_step(state):
        metadata = state.get("context_metadata", {})
        if not metadata.get("problems"):
            return "capture"
        current = metadata.get("problems_basis") == state["intent_metadata"]["single_statement_intent"]
        return "confirm" if current else "evaluate"

    def benefits_step(state):
        metadata = state["context_metadata"]
        if not metadata.get("benefits"):
            return "capture"
        return "confirm" if metadata.get("benefits_basis") == benefits_basis(state) else "evaluate"

    def after_problems_read_back(state):
        choice = state["context_metadata"]["choice"]
        return benefits_step(state) if choice == "yes" else choice

    ready = lambda state: state["context_metadata"]["ready"]

    builder.add_conditional_edges(
        START,
        problems_step,
        {
            "capture": "capture_current_situation",
            "evaluate": "evaluate_current_situation",
            "confirm": "confirm_current_situation",
        },
    )
    builder.add_edge("capture_current_situation", "evaluate_current_situation")
    builder.add_conditional_edges(
        "evaluate_current_situation",
        ready,
        {True: "confirm_current_situation", False: "capture_current_situation"},
    )
    builder.add_conditional_edges(
        "confirm_current_situation",
        after_problems_read_back,
        {
            "capture": "capture_expected_benefits",
            "evaluate": "evaluate_expected_benefits",
            "confirm": "confirm_expected_benefits",
            "no": "capture_current_situation",
            "sson": END,
        },
    )

    builder.add_edge("capture_expected_benefits", "evaluate_expected_benefits")
    builder.add_conditional_edges(
        "evaluate_expected_benefits",
        ready,
        {True: "confirm_expected_benefits", False: "capture_expected_benefits"},
    )
    builder.add_conditional_edges(
        "confirm_expected_benefits",
        lambda state: state["context_metadata"]["choice"],
        {
            "yes": END,
            "no": "capture_expected_benefits",
            "problems": "confirm_current_situation",
            "sson": END,
        },
    )

    return builder.compile(checkpointer=checkpointer)

# Standalone use keeps its own memory; embedded use inherits the parent's.
capture_context_graph = build_capture_context(checkpointer=InMemorySaver())
# capture_context_graph.get_graph(xray=True).draw_mermaid_png(
#     output_file_path="agentic_flow/capture_intent/context_expected_benefits_current_situation/capture_context_graph.png"
# )
