from langgraph.graph import END, START, StateGraph

from agentic_flow.goals.node import extract_goals, prepare_goal_request
from agentic_flow.state import AgentState


def build_goals(checkpointer=None):
    """Extract goals from the PRD in one pass without user interaction."""
    builder = StateGraph(AgentState)
    builder.add_node("prepare_goal_request", prepare_goal_request)
    builder.add_node("extract_goals", extract_goals)
    builder.add_edge(START, "prepare_goal_request")
    builder.add_edge("prepare_goal_request", "extract_goals")
    builder.add_edge("extract_goals", END)
    return builder.compile(checkpointer=checkpointer)
