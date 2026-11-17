from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from agentic_flow.state import AgentState
from agentic_flow.user_modelling.personas.node import (
    confirm_personas,
    evaluate_personas,
    finalize_personas,
    process_persona_response,
    prompt_persona_refinement,
    start_personas,
    personas_ready,
)


def build_personas(checkpointer=None):
    """Build the standalone persona flow, ending after explicit confirmation.

    Reuse a thread_id when resuming with Command(resume=...). The default
    exported graph retains current drafts and the latest exchange in memory.
    Without an explicit checkpointer, this builder inherits the parent graph's
    checkpointer when embedded. A caller can also supply a durable checkpointer.
    """
    builder = StateGraph(AgentState)
    builder.add_node("start_personas", start_personas)
    builder.add_node("process_persona_response", process_persona_response)
    builder.add_node("evaluate_personas", evaluate_personas)
    builder.add_node("refine_personas", prompt_persona_refinement)
    builder.add_node("confirm_personas", confirm_personas)
    builder.add_node("finalize_personas", finalize_personas)

    builder.add_edge(START, "start_personas")
    builder.add_edge("start_personas", "process_persona_response")
    builder.add_edge("process_persona_response", "evaluate_personas")
    builder.add_conditional_edges(
        "evaluate_personas",
        lambda state: "confirm" if personas_ready(state) else "refine",
        {"confirm": "confirm_personas", "refine": "refine_personas"},
    )
    builder.add_edge("refine_personas", "process_persona_response")
    builder.add_conditional_edges(
        "confirm_personas",
        lambda state: state["persona_metadata"]["user_confirmed"],
        {True: "finalize_personas", False: "process_persona_response"},
    )
    builder.add_edge("finalize_personas", END)

    return builder.compile(checkpointer=checkpointer)


persona_graph = build_personas(checkpointer=InMemorySaver())
# persona_graph.get_graph(xray=True).draw_mermaid_png(
#     output_file_path="agentic_flow/user_modelling/personas/persona_graph.png"
# )
