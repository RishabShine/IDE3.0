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


class PersonaRecord(TypedDict):
    persona_id: str
    stakeholder_id: str | None
    name: str
    role: str
    status_and_trust_level: str
    demographics: str
    ksa: str
    gmc: str
    usage_patterns: str
    varied_justification: str


PersonaVerdict = Literal["met", "not_met", "not_evaluated"]


class IndividualPersonaEvaluationRecord(TypedDict):
    persona_id: str
    relevance_verdict: PersonaVerdict
    relevance_feedback: str
    inferred_stakeholder_id: str | None
    name_verdict: PersonaVerdict
    name_feedback: str
    role_verdict: PersonaVerdict
    role_feedback: str
    status_and_trust_level_verdict: PersonaVerdict
    status_and_trust_level_feedback: str
    demographics_verdict: PersonaVerdict
    demographics_feedback: str
    ksa_verdict: PersonaVerdict
    ksa_feedback: str
    gmc_verdict: PersonaVerdict
    gmc_feedback: str
    usage_patterns_verdict: PersonaVerdict
    usage_patterns_feedback: str
    varied_verdict: PersonaVerdict
    varied_feedback: str
    varied_justification: str
    overall_verdict: PersonaVerdict


class SuggestedPersonaRecord(TypedDict):
    stakeholder_id: str
    description: str
    justification: str


class DeclinedPersonaSuggestionRecord(SuggestedPersonaRecord):
    reason: str


class PersonaEvaluationRecord(TypedDict):
    provided_personas: list[IndividualPersonaEvaluationRecord]
    suggested_personas: list[SuggestedPersonaRecord]


class PersonaMetadata(TypedDict):
    initialized: bool
    initial_context_message: str
    last_prompt_to_user: str
    drafts: list[PersonaRecord]
    next_draft_number: int
    draft_version: int
    pending_suggestions: list[SuggestedPersonaRecord]
    declined_suggestions: list[DeclinedPersonaSuggestionRecord]
    evaluation: PersonaEvaluationRecord | None
    evaluated_draft_version: int | None
    latest_user_response: str
    response_feedback: str
    user_confirmed: bool
    approved_version: int | None
    finalized_personas: list[PersonaRecord]


# the total agent memory state, which is a dictionary of all the states of the agent
class AgentState(TypedDict):

    project_context: str

    # Capture Intent State
    intent_metadata: IntentCapture

    # Full upstream intent snapshot, once the capture phase provides it.
    captured_intent: NotRequired[dict[str, Any]]

    # Current stakeholder drafts and latest exchange, saved by the checkpointer.
    stakeholder_metadata: NotRequired[StakeHolderMetadata]

    # Persona drafts and latest exchange; populated when the persona flow runs.
    persona_metadata: NotRequired[PersonaMetadata]
