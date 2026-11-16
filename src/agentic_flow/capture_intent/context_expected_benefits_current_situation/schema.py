"""
Structured output of the two evaluator LLMs. Verdicts only: the explanation goes in
feedback_to_user. The LLM only points at existing IDs; the node assigns new ones and
checks every source quote. What gets saved to AgentState is ContextCapture in agentic_flow/state.py.
"""

from pydantic import BaseModel, Field

from agentic_flow.state import Verdict


class ProblemCriteria(BaseModel):
    describes_current_state: Verdict
    specific: Verdict
    real_consequence: Verdict
    not_a_solution: Verdict
    relevant_to_sson: Verdict


class ExtractedProblem(BaseModel):
    id: str | None = Field(description="ID of the earlier item this keeps or rewrites, or null if new.")
    description: str = Field(description="The problem in the user's own words.")
    source: str | None = Field(description="Exact words from the user's latest message; null if unchanged.")
    criteria: ProblemCriteria


class CurrentSituationEvaluation(BaseModel):
    is_attempt: bool
    current_process: str | None = Field(description="How it works today, 1-3 sentences, user's facts only.")
    problems: list[ExtractedProblem]
    feedback_to_user: str
    suggested_example: str | None = Field(description="Null on attempt 1; from attempt 2, required if any item is not_met.")


class BenefitCriteria(BaseModel):
    outcome_not_feature: Verdict
    linked_to_problem: Verdict
    specific: Verdict
    measurable: Verdict
    supports_sson: Verdict


class ExtractedBenefit(BaseModel):
    id: str | None = Field(description="ID of the earlier item this keeps or rewrites, or null if new.")
    description: str = Field(description="The benefit in the user's own words.")
    source: str | None = Field(description="Exact words from the user's latest message; null if unchanged.")
    addresses: list[str] = Field(description="Problem IDs it fixes, e.g. ['Problem-1'].")
    measure: str | None = Field(description="The user's measure or target, or null.")
    criteria: BenefitCriteria


class ExpectedBenefitsEvaluation(BaseModel):
    is_attempt: bool
    benefits: list[ExtractedBenefit]
    out_of_scope_problems: list[str] = Field(description="Problem IDs the user said are out of scope.")
    feedback_to_user: str
    suggested_example: str | None = Field(description="Null on attempt 1; from attempt 2, required if any item is not_met.")
