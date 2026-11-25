from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import (
    START,
    END,
    StateGraph
)

from agentic_flow.state import AgentState
from agentic_flow.artifact_graph.graph import build_artifact_graph_step
from agentic_flow.capture_intent.graph import (
    build_capture_intent
)
from agentic_flow.user_modelling.graph import build_user_modelling
from agentic_flow.goals.graph import build_goals
from agentic_flow.use_cases.graph import build_use_cases


def build_ide3_chat(checkpointer=None):
    """The whole IDE3.0 flow. Its first input is the PRD, in the state:

        build_ide3_chat().invoke({"prd": prd_text}, config)

    capture intent -> user modelling -> goals -> use case model -> artifact graph.
    (goal2story, which writes user stories, is not part of the flow; it can still
    run on its own after the goals stage.)
    """
    builder = StateGraph(AgentState)

    # All subgraphs inherit this graph's checkpointing and thread context.
    builder.add_node("capture_intent_graph", build_capture_intent())
    builder.add_node("user_modelling_graph", build_user_modelling())
    builder.add_node("goals_graph", build_goals())
    builder.add_node("use_case_graph", build_use_cases())
    # links every artifact, the use cases included
    builder.add_node("artifact_graph_step", build_artifact_graph_step())

    builder.add_edge(START, "capture_intent_graph")
    builder.add_edge("capture_intent_graph", "user_modelling_graph")
    builder.add_edge("user_modelling_graph", "goals_graph")
    builder.add_edge("goals_graph", "use_case_graph")
    builder.add_edge("use_case_graph", "artifact_graph_step")
    builder.add_edge("artifact_graph_step", END)

    return builder.compile(
        checkpointer=checkpointer if checkpointer is not None else InMemorySaver()
    )


requirement_engineer = build_ide3_chat()
# To redraw every graph diagram, from src/:  python -m agentic_flow.draw_graphs


if __name__ == "__main__":
    # From src/:  python -m agentic_flow.graph  [--prd FILE] [--out FILE] [--quiet]
    # Asks you to paste a PRD first (unless --prd), then runs the whole flow with
    # real model calls and prints what each step produced.
    from agentic_flow.run import main

    main(default_step="main")
