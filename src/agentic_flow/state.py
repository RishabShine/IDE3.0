from typing import Any, Literal, NotRequired, TypedDict

Verdict = Literal["met", "partially_met", "not_met"]


class IntentCapture(TypedDict):
    single_statement_intent: str
    evaluation_of_statement: Verdict
    evaluation_of_statement_feedback: str
    attempt_number: int


class StakeHolderRecord(TypedDict):
    stakeholder_id: int
    name: str
    involvement: Literal["direct", "indirect"] | None
    summary: str
    justification: str


class StakeHolderMetadata(TypedDict):
    initialized: bool
    intent_context: dict[str, Any]
    initial_context_message: str
    last_prompt_to_user: str
    previous_evaluation: dict[str, Any] | None
    drafts: list[StakeHolderRecord]
    next_draft_id: int
    draft_version: int
    pending_suggestions: list[dict[str, str]]
    declined_suggestions: list[dict[str, str]]
    evaluation: dict[str, Any] | None
    latest_user_response: str
    response_feedback: str
    user_confirmed: bool
    approved_version: int | None
    finalized_stakeholders: list[StakeHolderRecord]


# the total agent memory state, which is a dictionary of all the states of the agent
class AgentState(TypedDict):

    project_context: str

    # Capture Intent State
    intent_metadata: IntentCapture

    # Full upstream intent snapshot, once the capture phase provides it.
    captured_intent: NotRequired[dict[str, Any]]

    # Current stakeholder drafts and latest exchange, saved by the checkpointer.
    stakeholder_metadata: NotRequired[StakeHolderMetadata]
