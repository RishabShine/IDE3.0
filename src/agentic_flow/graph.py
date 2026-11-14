from langgraph.graph import (
    START,
    END,
    StateGraph
)

from agentic_flow.state import AgentState
from agentic_flow.capture_intent.graph import (
    capture_intent_graph
)

def build_ide3_chat(): 

    builder = StateGraph(AgentState) 

    builder.add_node("capture_intent_graph", capture_intent_graph)

    builder.add_edge(START, "capture_intent_graph")

    builder.add_edge("capture_intent_graph", END)
    
    return builder.compile()

requirement_engineer = build_ide3_chat() 

