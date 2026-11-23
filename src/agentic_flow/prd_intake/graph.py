from langgraph.graph import END, START, StateGraph

from agentic_flow.prd_intake.node import intake_prd
from agentic_flow.state import AgentState


def build_prd_intake(checkpointer=None):
    builder = StateGraph(AgentState)
    builder.add_node("intake_prd", intake_prd)
    builder.add_edge(START, "intake_prd")
    builder.add_edge("intake_prd", END)
    return builder.compile(checkpointer=checkpointer)
