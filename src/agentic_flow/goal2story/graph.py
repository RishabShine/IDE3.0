from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from agentic_flow.goal2story import node
from agentic_flow.state import AgentState


def build_goal2story(checkpointer=None):
    """Build the Goal2Story flow: user stories for every extracted goal.

    initialize -> generate stories -> INVEST -> review ⇄ revise (-> INVEST)
    -> finalize. Reuse a thread_id when resuming with Command(resume=...).
    Without an explicit checkpointer, this builder inherits the parent graph's
    checkpointer when embedded.
    """
    builder = StateGraph(AgentState)
    builder.add_node("initialize_goal2story", node.initialize_goal2story)
    builder.add_node("generate_stories", node.generate_stories)
    builder.add_node("check_invest", node.check_invest)
    builder.add_node("review_stories", node.review_stories)
    builder.add_node("revise_stories", node.revise_stories)
    builder.add_node("finalize_goal2story", node.finalize_goal2story)

    builder.add_edge(START, "initialize_goal2story")
    # without extracted goals there is nothing to write stories for: skip to END
    builder.add_conditional_edges(
        "initialize_goal2story", node.has_goals, {True: "generate_stories", False: END},
    )
    # new or changed stories get an INVEST check before each review
    builder.add_edge("generate_stories", "check_invest")
    builder.add_edge("check_invest", "review_stories")
    builder.add_conditional_edges(
        "review_stories",
        node.route_review,
        {"approved": "finalize_goal2story", "revise": "revise_stories", "retry": "review_stories"},
    )
    builder.add_edge("revise_stories", "check_invest")
    builder.add_edge("finalize_goal2story", END)

    return builder.compile(checkpointer=checkpointer)


goal2story_graph = build_goal2story(checkpointer=InMemorySaver())
# To redraw the diagrams, from src/: python -m agentic_flow.draw_graphs
