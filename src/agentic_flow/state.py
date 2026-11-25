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
    project_context: NotRequired[str]

    # Raw PRD text, before any artifact extraction.
    prd: NotRequired[str]

    # Intent derived from the PRD by the capture-intent graph (see CapturedIntent).
    captured_intent: NotRequired[CapturedIntent]

    # Initial stakeholder extraction from the PRD, saved by the checkpointer.
    stakeholder_metadata: NotRequired[StakeHolderMetadata]

    # PRD-extracted personas; unresolved stakeholder links remain null.
    persona_metadata: NotRequired[PersonaMetadata]

    # Goal2Story impact map, review state and approved stories.
    goal2story_metadata: NotRequired[Goal2StoryMetadata]

    # Every extracted artifact and its links, assembled by the final step.
    artifact_graph: NotRequired[ArtifactGraph]
