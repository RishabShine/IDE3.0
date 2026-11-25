from langgraph.graph import END, START, StateGraph

from agentic_flow.artifact_graph.node import assemble_artifact_graph
from agentic_flow.state import AgentState


def build_artifact_graph_step(checkpointer=None):
    """Final step: assemble the extracted artifacts into one connected graph."""
    builder = StateGraph(AgentState)
    builder.add_node("assemble_artifact_graph", assemble_artifact_graph)
    builder.add_edge(START, "assemble_artifact_graph")
    builder.add_edge("assemble_artifact_graph", END)
    return builder.compile(checkpointer=checkpointer)
