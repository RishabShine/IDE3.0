from pydantic import Field

from agentic_flow.core.validation import StructuredRecord
from typing import Literal

Verdict = Literal["met", "not_met", "not_evaluated"]


class StakeHolderDraft(StructuredRecord):
    stakeholder_id: str
    name: str
    involvement: Literal["direct", "indirect"] | None
    summary: str
    justification: str


# A missing ID means a new group explicitly supplied by the user. The node,
# rather than the model, assigns its ID. Unknown draft details remain empty.
class StakeHolderDraftUpdate(StructuredRecord):
    stakeholder_id: str | None = Field(
        description="JSON null for a new record; copy an exact current draft ID for an edit. "
        "The application assigns new IDs. Never renumber existing records."
    )
    name: str = Field(description="Group or role name only; involvement is a separate field.")
    involvement: Literal["direct", "indirect"] | None = Field(
        description="Preserve the user's explicit classification or the unchanged draft value. "
        "Use null only when unknown; do not reclassify based on examples or your own judgement."
    )
    summary: str
    justification: str


class StakeHolderResponse(StructuredRecord):
    updates: list[StakeHolderDraftUpdate]
    removed_stakeholder_ids: list[str]
    clarification_feedback: str

# eval for stakeholders that the user has agreed on
class IndividualStakeHolderEvaluation(StructuredRecord):
    stakeholder_id: str
    detail_verdict: Verdict
    detail_feedback: str
    relevance_verdict: Verdict
    relevance_feedback: str
    overlap_verdict: Verdict
    overlap_feedback: str
    overlap_stakeholder_ids: list[str]
    overall_verdict: Verdict


class StakeHolderEvaluation(StructuredRecord):
    provided_stakeholders: list[IndividualStakeHolderEvaluation]
