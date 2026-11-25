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


class StakeHolderMetadata(TypedDict):
    # Prepared instructions and input context for the initial PRD extraction.
    instructions: str
    stakeholders: list[StakeHolderRecord]


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


class PersonaMetadata(TypedDict):
    # Prepared instructions and input context for the initial PRD extraction.
    instructions: str
    personas: list[PersonaRecord]


class Goal2StoryMetadata(TypedDict):
    initialized: bool
    # PRD mode: goal taken from the PRD, every level accepted without review
    auto: bool
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

    #! older from the iterative process, can remove once we fix functionality got PRD
    project_context: str

    # Raw PRD text, before any artifact extraction.
    prd: NotRequired[str]

    # Capture Intent State
    intent_metadata: IntentCapture

    # Full upstream intent snapshot, once the capture phase provides it.
    captured_intent: NotRequired[dict[str, Any]]

    # Initial stakeholder extraction from the PRD, saved by the checkpointer.
    stakeholder_metadata: NotRequired[StakeHolderMetadata]

    # PRD-extracted personas; unresolved stakeholder links remain null.
    persona_metadata: NotRequired[PersonaMetadata]

    # Goal2Story impact map, review state and approved stories.
    goal2story_metadata: NotRequired[Goal2StoryMetadata]
