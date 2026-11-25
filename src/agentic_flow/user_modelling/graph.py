from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from agentic_flow.state import AgentState
from agentic_flow.user_modelling.personas.graph import build_personas
from agentic_flow.user_modelling.stakeholders.graph import build_stakeholders


def build_user_modelling(checkpointer=None):
    """Extract stakeholders, then personas, without user interaction."""
    builder = StateGraph(AgentState)
    builder.add_node("stakeholders", build_stakeholders())
    builder.add_node("personas", build_personas())
    builder.add_edge(START, "stakeholders")
    builder.add_edge("stakeholders", "personas")
    builder.add_edge("personas", END)
    return builder.compile(checkpointer=checkpointer)


user_modelling_graph = build_user_modelling(checkpointer=InMemorySaver())
# To redraw the diagrams, from src/: python -m agentic_flow.draw_graphs
