from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from agentic_flow.goal2story import node
from agentic_flow.state import AgentState

# generate → (INVEST, stories only) → review ⇄ revise, then the next level
GENERATE = {
    "actors": node.generate_actors,
    "impacts": node.generate_impacts,
    "deliverables": node.generate_deliverables,
    "stories": node.generate_stories,
}
REVIEW = {
    "actors": node.review_actors,
    "impacts": node.review_impacts,
    "deliverables": node.review_deliverables,
    "stories": node.review_stories,
}
REVISE = {
    "actors": node.revise_actors,
    "impacts": node.revise_impacts,
    "deliverables": node.revise_deliverables,
    "stories": node.revise_stories,
}
NEXT = {
    "actors": "generate_impacts",
    "impacts": "generate_deliverables",
    "deliverables": "generate_stories",
    "stories": "finalize_goal2story",
}


def build_goal2story(checkpointer=None):
    """Build the Goal2Story flow (lane 3).

    Reuse a thread_id when resuming with Command(resume=...). Without an
    explicit checkpointer, this builder inherits the parent graph's
    checkpointer when embedded.
    """
    builder = StateGraph(AgentState)
    builder.add_node("initialize_goal2story", node.initialize_goal2story)
    builder.add_node("confirm_goal", node.confirm_goal)
    builder.add_node("check_invest", node.check_invest)
    builder.add_node("finalize_goal2story", node.finalize_goal2story)

    builder.add_edge(START, "initialize_goal2story")
    builder.add_edge("initialize_goal2story", "confirm_goal")
    builder.add_conditional_edges(
        "confirm_goal",
        node.goal_confirmed,
        {True: "generate_actors", False: "confirm_goal"},
    )

    for level in node.LEVELS:
        generate, review, revise = f"generate_{level}", f"review_{level}", f"revise_{level}"
        builder.add_node(generate, GENERATE[level])
        builder.add_node(review, REVIEW[level])
        builder.add_node(revise, REVISE[level])

        # new or changed stories get an INVEST check before each review
        after_change = "check_invest" if level == "stories" else review
        builder.add_edge(generate, after_change)
        builder.add_edge(revise, after_change)
        builder.add_conditional_edges(
            review,
            node.make_review_router(level),
            {"approved": NEXT[level], "revise": revise, "retry": review},
        )

    builder.add_edge("check_invest", "review_stories")
    builder.add_edge("finalize_goal2story", END)

    return builder.compile(checkpointer=checkpointer)


goal2story_graph = build_goal2story(checkpointer=InMemorySaver())
# goal2story_graph.get_graph(xray=True).draw_mermaid_png(
#     output_file_path="agentic_flow/goal2story/goal2story_graph.png"
# )
