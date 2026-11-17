from typing import Any, Literal, NotRequired, TypedDict

Verdict = Literal["met", "partially_met", "not_met"]


class IntentCapture(TypedDict):
    single_statement_intent: str
    evaluation_of_statement: Verdict
    evaluation_of_statement_feedback: str
    attempt_number: int


class StakeHolderRecord(TypedDict):
    stakeholder_id: str
    name: str
    involvement: Literal["direct", "indirect"] | None
    summary: str
    justification: str


StakeHolderVerdict = Literal["met", "not_met", "not_evaluated"]


class IndividualStakeHolderEvaluationRecord(TypedDict):
    stakeholder_id: str
    detail_verdict: StakeHolderVerdict
    detail_feedback: str
    relevance_verdict: StakeHolderVerdict
    relevance_feedback: str
    overlap_verdict: StakeHolderVerdict
    overlap_feedback: str
    overlap_stakeholder_ids: list[str]
    overall_verdict: StakeHolderVerdict


class SuggestedStakeHolderRecord(TypedDict):
    name: str
    summary: str
    justification: str


# Dictionary form of the full StakeHolderEvaluation Pydantic response.
class StakeHolderEvaluationRecord(TypedDict):
    provided_stakeholders: list[IndividualStakeHolderEvaluationRecord]
    suggested_stakeholders: list[SuggestedStakeHolderRecord]


class StakeHolderMetadata(TypedDict):
    initialized: bool
    initial_context_message: str
    last_prompt_to_user: str
    drafts: list[StakeHolderRecord]
    next_draft_number: int
    draft_version: int
    pending_suggestions: list[dict[str, str]]
    declined_suggestions: list[dict[str, str]]
    evaluation: StakeHolderEvaluationRecord | None
    evaluated_draft_version: int | None
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
