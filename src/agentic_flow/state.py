from typing import Any, Literal, NotRequired, TypedDict

from langchain_core.messages import BaseMessage

Verdict = Literal["met", "partially_met", "not_met"]


class IntentCapture(TypedDict):
    single_statement_intent: str
    evaluation_of_statement: Verdict
    evaluation_of_statement_feedback: str
    attempt_number: int


class StakeHolderMetadata(TypedDict):
    initialized: bool
    intent_context: dict[str, Any]
    messages: list[BaseMessage]
    drafts: list[dict[str, Any]]
    next_draft_id: int
    draft_version: int
    pending_suggestions: list[dict[str, str]]
    declined_suggestions: list[dict[str, str]]
    evaluation: dict[str, Any] | None
    latest_user_response: str
    response_feedback: str
    user_confirmed: bool
    approved_version: int | None
    finalized_stakeholders: list[dict[str, Any]]


class Goal2StoryMetadata(TypedDict):
    initialized: bool
    n_per_parent: int
    context: dict[str, Any]
    proposed_goal: str
    goal: str
    goal_confirmed: bool
    # each item: id, parent_id and its level's fields (see goal2story/schema.py)
    actors: list[dict[str, Any]]
    impacts: list[dict[str, Any]]
    deliverables: list[dict[str, Any]]
    stories: list[dict[str, Any]]
    next_index: dict[str, int]
    latest_user_response: str
    response_feedback: str
    approved_levels: list[str]
    edit_log: list[dict[str, Any]]
    open_questions: list[dict[str, str]]
    finalized_stories: list[dict[str, Any]]


# the total agent memory state, which is a dictionary of all the states of the agent
class AgentState(TypedDict):

    project_context: str

    # Capture Intent State
    intent_metadata: IntentCapture

    # Full upstream intent snapshot, once the capture phase provides it.
    captured_intent: NotRequired[dict[str, Any]]

    # Stakeholder conversation and drafts, saved together by the checkpointer.
    stakeholder_metadata: NotRequired[StakeHolderMetadata]

    # Goal2Story impact map, review state and approved stories.
    goal2story_metadata: NotRequired[Goal2StoryMetadata]
