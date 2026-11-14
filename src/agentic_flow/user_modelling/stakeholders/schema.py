from pydantic import BaseModel
from typing import Literal

Verdict = Literal["met", "not_met", "not_evaluated"]

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
