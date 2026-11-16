from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import (
    START,
    END,
    StateGraph
)

from agentic_flow.state import AgentState
from agentic_flow.capture_intent.graph import (
    build_capture_intent
)
from agentic_flow.user_modelling.graph import build_user_modelling

def build_ide3_chat(checkpointer=None):

    builder = StateGraph(AgentState) 

    # Both subgraphs inherit this graph's checkpointing and thread context.
    builder.add_node("capture_intent_graph", build_capture_intent())
    builder.add_node("user_modelling_graph", build_user_modelling())

    builder.add_edge(START, "capture_intent_graph")

    builder.add_edge("capture_intent_graph", "user_modelling_graph")
    builder.add_edge("user_modelling_graph", END)
    
    return builder.compile(
        checkpointer=checkpointer if checkpointer is not None else InMemorySaver()
    )

requirement_engineer = build_ide3_chat()
# requirement_engineer.get_graph(xray=True).draw_mermaid_png(
#     output_file_path="agentic_flow/requirement_engineer_graph.png"
# )
