from pydantic import BaseModel
from typing import Literal

Verdict = Literal["met", "not_met", "not_evaluated"]


class StakeHolderDraft(BaseModel):
    stakeholder_id: int
    name: str
    involvement: Literal["direct", "indirect"] | None
    summary: str
    justification: str


# A missing ID means a new group explicitly supplied by the user. The node,
# rather than the model, assigns its ID. Unknown draft details remain empty.
class StakeHolderDraftUpdate(BaseModel):
    stakeholder_id: int | None
    name: str
    involvement: Literal["direct", "indirect"] | None
    summary: str
    justification: str


class StakeHolderSuggestionDecision(BaseModel):
    name: str
    decision: Literal["accept", "decline"]
    reason: str


class StakeHolderResponse(BaseModel):
    updates: list[StakeHolderDraftUpdate]
    removed_stakeholder_ids: list[int]
    suggestion_decisions: list[StakeHolderSuggestionDecision]
    clarification_feedback: str

# eval for stakeholders that the user has agreed on
class IndividualStakeHolderEvaluation(BaseModel):
    stakeholder_id: int
    detail_verdict: Verdict
    detail_feedback: str
    relevance_verdict: Verdict
    relevance_feedback: str
    overlap_verdict: Verdict
    overlap_feedback: str
    overlap_stakeholder_ids: list[int]
    overall_verdict: Verdict

# stakeholders the user potentially missed
class SuggestedStakeHolder(BaseModel):
    name: str
    summary: str
    justification: str

class StakeHolderEvaluation(BaseModel):
    provided_stakeholders: list[IndividualStakeHolderEvaluation]
    suggested_stakeholders: list[SuggestedStakeHolder]
