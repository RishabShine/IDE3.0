from pydantic import BaseModel
from typing import Literal

Verdict = Literal["met", "not_met", "not_evaluated"]


class PersonaDraft(BaseModel):
    persona_id: str
    # Unknown until the user supplies or confirms the corresponding stakeholder.
    stakeholder_id: str | None
    name: str
    role: str
    status_and_trust_level: str
    # Optional in the lecture template; an empty string is acceptable.
    demographics: str
    # Knowledge, skills, abilities.
    ksa: str
    # Goals, motives, concerns.
    gmc: str
    usage_patterns: str
    # Generated from a passing evaluation, not required from the user.
    varied_justification: str = ""


# The node assigns Persona-1, Persona-2, etc. to new drafts. A missing
# stakeholder reference stays unresolved rather than inventing a stakeholder.
class PersonaDraftUpdate(BaseModel):
    persona_id: str | None
    stakeholder_id: str | None
    name: str
    role: str
    status_and_trust_level: str
    demographics: str
    ksa: str
    gmc: str
    usage_patterns: str
    varied_justification: str = ""


class PersonaResponse(BaseModel):
    updates: list[PersonaDraftUpdate]
    removed_persona_ids: list[str]
    clarification_feedback: str


class IndividualPersonaEvaluation(BaseModel):
    persona_id: str
    # Relevance covers the stakeholder match and consistency with known intent.
    # Missing context is not evidence of irrelevance. If relevance is not met
    # or cannot be established, other verdicts are not_evaluated.
    relevance_verdict: Verdict
    relevance_feedback: str
    # A proposed existing stakeholder ID, not an automatically confirmed link.
    inferred_stakeholder_id: str | None
    name_verdict: Verdict
    name_feedback: str
    role_verdict: Verdict
    role_feedback: str
    status_and_trust_level_verdict: Verdict
    status_and_trust_level_feedback: str
    # Missing optional demographics can be met without inventing personal facts.
    demographics_verdict: Verdict
    demographics_feedback: str
    ksa_verdict: Verdict
    ksa_feedback: str
    gmc_verdict: Verdict
    gmc_feedback: str
    usage_patterns_verdict: Verdict
    usage_patterns_feedback: str
    varied_verdict: Verdict
    varied_feedback: str
    # Explain Vivid, Actionable, Real, Identifiable, Exact, and Detailed using
    # supplied information. Populate only on overall met, otherwise use "".
    # The eventual node copies this to the draft after a passing evaluation.
    varied_justification: str
    overall_verdict: Verdict


class PersonaEvaluation(BaseModel):
    provided_personas: list[IndividualPersonaEvaluation]
