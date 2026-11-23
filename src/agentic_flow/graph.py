from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import (
    START,
    END,
    StateGraph
)

from agentic_flow.state import AgentState
from agentic_flow.prd_intake.graph import build_prd_intake
from agentic_flow.capture_intent.graph import (
    build_capture_intent
)
from agentic_flow.user_modelling.graph import build_user_modelling
from agentic_flow.goal2story.graph import build_goal2story

def build_ide3_chat(checkpointer=None):

    builder = StateGraph(AgentState) 

    # All subgraphs inherit this graph's checkpointing and thread context.
    builder.add_node("prd_intake_graph", build_prd_intake())
    builder.add_node("capture_intent_graph", build_capture_intent())
    builder.add_node("user_modelling_graph", build_user_modelling())
    builder.add_node("goal2story_graph", build_goal2story())

    builder.add_edge(START, "prd_intake_graph")
    # (after adding PRD intake) keep the existing flow connected until PRD processing is implemented.
    builder.add_edge("prd_intake_graph", "capture_intent_graph")

    builder.add_edge("capture_intent_graph", "user_modelling_graph")
    builder.add_edge("user_modelling_graph", "goal2story_graph")
    builder.add_edge("goal2story_graph", END)
    
    return builder.compile(
        checkpointer=checkpointer if checkpointer is not None else InMemorySaver()
    )

requirement_engineer = build_ide3_chat()
# requirement_engineer.get_graph(xray=True).draw_mermaid_png(
#     output_file_path="agentic_flow/requirement_engineer_graph.png"
# )
