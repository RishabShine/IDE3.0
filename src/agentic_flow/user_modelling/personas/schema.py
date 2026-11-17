from pydantic import BaseModel
from typing import Literal

Verdict = Literal["met", "not_met", "not_evaluated"]


class PersonaDraft(BaseModel):
    persona_id: str
    stakeholder_id: str
    name: str
    status_and_trust_level: str
    demographics: str
    # knowledge, skills, abilities
    ksa: str
    # goals, motives, concerns
    gmc: str
    usage_patterns: str
    varied_justification: str


# A missing ID means a new group explicitly supplied by the user. The node,
# rather than the model, assigns its ID. Unknown draft details remain empty.
class PersonaDraftUpdate(BaseModel):
    persona_id: str
    stakeholder_id: str
    name: str
    status_and_trust_level: str
    demographics: str
    # knowledge, skills, abilities
    ksa: str
    # goals, motives, concerns
    gmc: str
    usage_patterns: str
    varied_justification: str


class PersonaSuggestionDecision(BaseModel):
    description: str
    decision: Literal["accept", "decline"]
    reason: str


class StakeHolderResponse(BaseModel):
    updates: list[PersonaDraftUpdate]
    removed_persona_ids: list[int]
    suggestion_decisions: list[PersonaSuggestionDecision]
    clarification_feedback: str

# eval for stakeholders that the user has agreed on
class IndividualPersonaEvaluation(BaseModel):
    persona_id: int
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
