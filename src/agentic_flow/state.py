from typing import Any, Literal, NotRequired, TypedDict

from agentic_flow.artifact_graph.schema import ArtifactGraph

Verdict = Literal["met", "partially_met", "not_met"]


# Capture intent (PEGS G.1-G.3, E.5-E.6), derived from the PRD
# -----------------------------------------------------------------------------
# Anything the PRD does not state but we derived anyway starts with RED_FLAG.
# A list item whose source quote is not found in the PRD is flagged the same way
# and keeps source=None.

RED_FLAG = "\U0001F6A9"  # the red flag emoji


class SourcedItem(TypedDict):
    id: str
    description: str
    # exact words from the PRD this item comes from, or None if not found there
    source: str | None


class BenefitRecord(SourcedItem):
    addresses: list[str]  # Problem IDs this benefit fixes
    measure: str | None  # target copied from the PRD, or None
    kind: Literal["hard", "soft"]  # hard when it has a measure


class SSONCriterionRecord(TypedDict):
    verdict: Verdict
    reason: str


class SSONEvaluationRecord(TypedDict):
    # non-blocking quality check; nothing waits on it, it only reports gaps
    criteria: dict[str, SSONCriterionRecord]
    score: int
    passed: bool
    feedback: str


class CapturedIntent(TypedDict, total=False):
    # G.1 Context and overall objective, with the SSON
    single_statement_intent: str
    sson_source: Literal["stated", "synthesized"]
    sson_evidence: list[str]  # PRD sentences the SSON is built from
    what: str | None
    how: str | None
    why: str | None
    success_measure: str | None
    context_and_objective: str
    sson_evaluation: SSONEvaluationRecord
    # G.2 Current situation
    current_situation: str
    problems: list[SourcedItem]  # Problem-n
    # G.3 Expected benefits
    benefits: list[BenefitRecord]  # Benefit-n
    out_of_scope_problems: list[str]
    # E.5 Effects, E.6 Invariants, plus constraints and scope exclusions
    effects: list[SourcedItem]  # Effect-n
    invariants: list[SourcedItem]  # Invariant-n
    constraints: list[SourcedItem]  # Constraint-n
    scope_exclusions: list[SourcedItem]  # Exclusion-n


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
    statement: str  # starts with RED_FLAG when no PRD quote supports it
    source: str | None  # exact PRD words, or None if not found there
    benefit_ids: list[str]  # Benefit IDs that show the goal is reached
    actors: list[GoalActorRecord]
    goal_type: Literal["hard", "soft"] | None
    resources: list[str]
    plans: str
    justification: str


class GoalMetadata(TypedDict):
    # Prepared instructions and input context for the initial PRD extraction.
    instructions: str
    goals: list[GoalRecord]


class UseCaseActorRecord(TypedDict):
    actor_id: str  # Actor-n
    name: str
    kind: Literal["human", "system", "organization"]
    stakeholder_id: str | None


class UseCaseRecord(TypedDict):
    use_case_id: str  # UC-n
    name: str  # infinitive verb phrase
    description: str
    primary_actor_id: str | None
    supporting_actor_ids: list[str]
    goal_ids: list[str]


class UseCaseRelationshipRecord(TypedDict):
    kind: Literal["include", "extend"]
    source: str  # include: base use case; extend: the extending use case
    target: str  # include: included use case; extend: the base use case
    condition: str  # extend only


class UseCaseMetadata(TypedDict):
    # Prepared instructions and input context for the modelling call.
    instructions: str
    system_name: str
    actors: list[UseCaseActorRecord]
    use_cases: list[UseCaseRecord]
    relationships: list[UseCaseRelationshipRecord]
    issues: list[str]  # rough-model checks from the L13 pitfalls


class Goal2StoryMetadata(TypedDict):
    initialized: bool
    # PRD mode: stories accepted as written, with no review stop
    auto: bool
    stories_per_goal: int
    context: dict[str, Any]
    # the extracted goals the stories are written for (from goal_metadata), each
    # with id, statement, goal_type, actors, resources, plans, justification
    # and delivers_benefits
    goals: list[dict[str, Any]]
    # each story: id (US-n), parent_id (its goal), actor, action,
    # expected_outcome, stakeholder_id, text, invest
    stories: list[dict[str, Any]]
    next_index: int
    latest_user_response: str
    response_feedback: str
    approved: bool
    edit_log: list[dict[str, Any]]
    open_questions: list[dict[str, str]]
    finalized_stories: list[dict[str, Any]]
    skipped: bool  # True when there were no goals, so no stories were written


# the total agent memory state, which is a dictionary of all the states of the agent
class AgentState(TypedDict):

    #! older from the iterative process, can remove once we fix functionality got PRD
    project_context: NotRequired[str]

    # Raw PRD text, before any artifact extraction.
    prd: NotRequired[str]

    # Intent derived from the PRD by the capture-intent graph (see CapturedIntent).
    captured_intent: NotRequired[CapturedIntent]

    # Initial stakeholder extraction from the PRD, saved by the checkpointer.
    stakeholder_metadata: NotRequired[StakeHolderMetadata]

    # PRD-extracted personas; unresolved stakeholder links remain null.
    persona_metadata: NotRequired[PersonaMetadata]

    # PRD-extracted goals and their supplied actors, resources, plans, and rationale.
    goal_metadata: NotRequired[GoalMetadata]

    # Impact analysis: the edits to assess ({"changes": [...]}) and the resulting
    # report of proposals for linked artifacts (see impact_analysis/node.py).
    impact_request: NotRequired[dict[str, Any]]
    impact_report: NotRequired[dict[str, Any]]

    # Rough use case model (L13): actors, use cases, «include»/«extend», checks.
    use_case_metadata: NotRequired[UseCaseMetadata]

    # Goal2Story: user stories per extracted goal, review state, approved stories.
    goal2story_metadata: NotRequired[Goal2StoryMetadata]

    # Every extracted artifact and its links, assembled by the final step.
    artifact_graph: NotRequired[ArtifactGraph]
