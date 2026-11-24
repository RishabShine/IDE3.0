from langgraph.graph import END, START, StateGraph

from agentic_flow.state import AgentState
from agentic_flow.user_modelling.personas.node import (
    extract_personas,
    prepare_persona_request,
)


def build_personas(checkpointer=None):
    builder = StateGraph(AgentState)
    builder.add_node("prepare_persona_request", prepare_persona_request)
    builder.add_node("extract_personas", extract_personas)
    builder.add_edge(START, "prepare_persona_request")
    builder.add_edge("prepare_persona_request", "extract_personas")
    builder.add_edge("extract_personas", END)
    return builder.compile(checkpointer=checkpointer)
