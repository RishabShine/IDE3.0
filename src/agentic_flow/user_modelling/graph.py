from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from agentic_flow.state import AgentState
from agentic_flow.user_modelling.stakeholders.node import (
    confirm_stakeholders,
    evaluate_stakeholders,
    finalize_stakeholders,
    initialize_stakeholders,
    process_stakeholder_response,
    prompt_initial_stakeholders,
    prompt_stakeholder_refinement,
    stakeholders_ready,
)


def build_user_modelling(checkpointer=None):
    """Build the stakeholder flow; personas and handoff can be added later.

    Reuse a thread_id when resuming with Command(resume=...). The default
    exported graph retains the conversation in memory while the process runs.
    Without an explicit checkpointer, this builder inherits the parent graph's
    checkpointer when embedded. A caller can also supply a durable checkpointer.
    """
    builder = StateGraph(AgentState)
    builder.add_node("initialize_stakeholders", initialize_stakeholders)
    builder.add_node("initial_stakeholder_input", prompt_initial_stakeholders)
    builder.add_node("process_stakeholder_response", process_stakeholder_response)
    builder.add_node("evaluate_stakeholders", evaluate_stakeholders)
    builder.add_node("refine_stakeholders", prompt_stakeholder_refinement)
    builder.add_node("confirm_stakeholders", confirm_stakeholders)
    builder.add_node("finalize_stakeholders", finalize_stakeholders)

    builder.add_edge(START, "initialize_stakeholders")
    builder.add_edge("initialize_stakeholders", "initial_stakeholder_input")
    builder.add_edge("initial_stakeholder_input", "process_stakeholder_response")
    builder.add_edge("process_stakeholder_response", "evaluate_stakeholders")
    builder.add_conditional_edges(
        "evaluate_stakeholders",
        lambda state: "confirm" if stakeholders_ready(state) else "refine",
        {"confirm": "confirm_stakeholders", "refine": "refine_stakeholders"},
    )
    builder.add_edge("refine_stakeholders", "process_stakeholder_response")
    builder.add_conditional_edges(
        "confirm_stakeholders",
        lambda state: state["stakeholder_metadata"]["user_confirmed"],
        {True: "finalize_stakeholders", False: "process_stakeholder_response"},
    )
    builder.add_edge("finalize_stakeholders", END)

    return builder.compile(checkpointer=checkpointer)


user_modelling_graph = build_user_modelling(checkpointer=InMemorySaver())
# user_modelling_graph.get_graph(xray=True).draw_mermaid_png(
#     output_file_path="agentic_flow/user_modelling/user_modelling_graph.png"
# )
