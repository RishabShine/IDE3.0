from pydantic import BaseModel, Field

from agentic_flow.state import Verdict


class CriterionResult(BaseModel):
    verdict: Verdict
    evidence: str = Field(description="Exact quote from the statement supporting the verdict, or 'none'.")
    reason: str = Field(description="One sentence explaining the verdict.")


class SSONCriteria(BaseModel):
    clear_and_concise: CriterionResult
    goal_and_how: CriterionResult
    names_capability: CriterionResult
    need_not_want: CriterionResult
    success_condition: CriterionResult


# The evaluator LLM's output. The score and pass/fail are computed in code.
class SSONEvaluation(BaseModel):
    is_sson_attempt: bool
    what: str | None = Field(description="Capability the system provides, in the user's words.")
    how: str | None = Field(description="Main means of delivering it.")
    why: str | None = Field(description="Underlying need, problem, or opportunity.")
    success_measure: str | None = Field(description="Outcome to check requirements against.")
    criteria: SSONCriteria
    feedback_to_user: str
    suggested_revision: str | None = None
