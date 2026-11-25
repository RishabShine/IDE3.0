from langgraph.graph import END, START, StateGraph

from agentic_flow.state import AgentState
from agentic_flow.use_cases.node import extract_use_cases, prepare_use_case_request


def build_use_cases(checkpointer=None):
    """A rough use case model (3RA3 L13) from the PRD, user model and goals."""
    builder = StateGraph(AgentState)
    builder.add_node("prepare_use_case_request", prepare_use_case_request)
    builder.add_node("extract_use_cases", extract_use_cases)
    builder.add_edge(START, "prepare_use_case_request")
    builder.add_edge("prepare_use_case_request", "extract_use_cases")
    builder.add_edge("extract_use_cases", END)
    return builder.compile(checkpointer=checkpointer)
