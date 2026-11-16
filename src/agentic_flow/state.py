from typing import Any, Literal, NotRequired, TypedDict

from langchain_core.messages import BaseMessage

Verdict = Literal["met", "partially_met", "not_met"]


class IntentCapture(TypedDict, total=False):
    single_statement_intent: str    # the user's statement, verbatim
    what: str | None
    how: str | None
    why: str | None
    success_measure: str | None
    evaluation_score: int           # 0-100, computed in code
    passed: bool
    feedback: str                   # shown to the user on the next attempt
    attempt_number: int


class Problem(TypedDict):
    id: str                         # "Problem-1", assigned by code, never reused
    description: str
    source: str                     # the user's own words it was extracted from


class Benefit(TypedDict):
    id: str                         # "Benefit-1", assigned by code, never reused
    description: str
    source: str                     # the user's own words it was extracted from
    addresses: list[str]            # problem IDs it fixes (L28 Justified / Traceable)
    measure: str | None
    kind: Literal["hard", "soft"]   # soft = no measure yet, defined later (L08)


# Current situation (G.2) and expected benefits (G.3).
class ContextCapture(TypedDict, total=False):
    user_input: str                 # latest reply; "" once the evaluator has used it
    feedback: str                   # shown to the user on the next prompt
    passed: bool                    # every item in the stage in progress passes
    ready: bool                     # passed, or the tries ran out: go to the read-back
    attempts: int                   # evaluations since the last read-back
    asked_about: list[str]          # IDs the last feedback asked the user about
    choice: Literal["yes", "no", "sson", "problems"]    # answer to the last read-back
    next_problem_id: int
    next_benefit_id: int
    problems_basis: str             # the SSON the problems were last graded against
    benefits_basis: dict[str, Any]  # the SSON + problems the benefits were graded against
    current_process: str | None
    problems: list[Problem]
    benefits: list[Benefit]
    out_of_scope_problems: list[str]    # problem IDs, destined for G.6


class StakeHolderMetadata(TypedDict):
    initialized: bool
    intent_context: dict[str, Any]
    messages: list[BaseMessage]
    drafts: list[dict[str, Any]]
    next_draft_id: int
    draft_version: int
    pending_suggestions: list[dict[str, str]]
    declined_suggestions: list[dict[str, str]]
    evaluation: dict[str, Any] | None
    latest_user_response: str
    response_feedback: str
    user_confirmed: bool
    approved_version: int | None
    finalized_stakeholders: list[dict[str, Any]]


# the total agent memory state, which is a dictionary of all the states of the agent
class AgentState(TypedDict):

    project_context: str

    # Capture Intent State
    intent_metadata: IntentCapture
    context_metadata: NotRequired[ContextCapture]

    # Full upstream intent snapshot, once the capture phase provides it.
    captured_intent: NotRequired[dict[str, Any]]

    # Stakeholder conversation and drafts, saved together by the checkpointer.
    stakeholder_metadata: NotRequired[StakeHolderMetadata]
