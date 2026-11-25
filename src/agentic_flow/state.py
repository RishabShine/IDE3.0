from typing import Any, Literal, NotRequired, TypedDict

from agentic_flow.artifact_graph.schema import ArtifactGraph

Verdict = Literal["met", "partially_met", "not_met"]


class IntentCapture(TypedDict):
    single_statement_intent: str
    # Kept for compatibility; PRD-derived intent is stored as "met" after extraction.
    evaluation_of_statement: Verdict
    evaluation_of_statement_feedback: str
    attempt_number: int
    # Temporary prompt text used between prepare and extract; cleared after extract.
    instructions: NotRequired[str]


class CapturedIntent(TypedDict):
    """Structured intent derived from the PRD for downstream extraction and the artifact graph."""

    single_statement_intent: str
    what: NotRequired[str]
    how: NotRequired[str]
    why: NotRequired[str]
    success_measure: NotRequired[str]
    current_process: NotRequired[str]
    problems: NotRequired[list[dict[str, Any]]]
    benefits: NotRequired[list[dict[str, Any]]]
    goals: NotRequired[list[Any]]


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


class GoalActorRecord(TypedDict):
    name: str
    stakeholder_id: str | None
    role: str
    involvement: str


class GoalRecord(TypedDict):
    goal_id: str
    statement: str
    actors: list[GoalActorRecord]
    goal_type: Literal["hard", "soft"] | None
    resources: list[str]
    plans: str
    justification: str


class GoalMetadata(TypedDict):
    # Prepared instructions and input context for the initial PRD extraction.
    instructions: str
    goals: list[GoalRecord]


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

    # Full intent snapshot derived from the PRD (SSON, problems, benefits, goals).
    captured_intent: NotRequired[CapturedIntent]

    # Initial stakeholder extraction from the PRD, saved by the checkpointer.
    stakeholder_metadata: NotRequired[StakeHolderMetadata]

    # PRD-extracted personas; unresolved stakeholder links remain null.
    persona_metadata: NotRequired[PersonaMetadata]

    # PRD-extracted goals and their supplied actors, resources, plans, and rationale.
    goal_metadata: NotRequired[GoalMetadata]

    # Goal2Story impact map, review state and approved stories.
    goal2story_metadata: NotRequired[Goal2StoryMetadata]

    # Every extracted artifact and its links, assembled by the final step.
    artifact_graph: NotRequired[ArtifactGraph]
