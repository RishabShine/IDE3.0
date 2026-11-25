from pydantic import BaseModel, Field

from agentic_flow.state import Verdict


# Extraction: the SSON and G.1 from the PRD
# -----------------------------------------------------------------------------

class SSONExtraction(BaseModel):
    stated_sson: str | None = Field(
        description="A sentence from the PRD that already works as the SSON, copied "
        "word for word. Null if the PRD has no such sentence."
    )
    synthesized_sson: str = Field(
        description="A 1-3 sentence SSON built only from facts in the PRD: the need, the "
        "capability, the main way it is delivered, and how success would be judged."
    )
    evidence: list[str] = Field(
        description="The PRD sentences the SSON is built from, each copied word for word."
    )
    what: str | None = Field(description="The capability the system will provide.")
    how: str | None = Field(description="The main way it will deliver that capability.")
    why: str | None = Field(description="The underlying need, problem or opportunity.")
    success_measure: str | None = Field(
        description="The outcome to check requirements against, using only targets the "
        "PRD gives. Null if the PRD gives no way to tell the need was met."
    )
    context_and_objective: str = Field(
        description="G.1: why the project is needed, its business context and overall "
        "objective, in 1-3 sentences from the PRD. Empty string if absent."
    )


# Non-blocking evaluation of the SSON against the 3RA3 L04 criteria
# -----------------------------------------------------------------------------

class CriterionResult(BaseModel):
    verdict: Verdict
    reason: str = Field(description="One sentence explaining the verdict.")


class SSONCriteria(BaseModel):
    clear_and_concise: CriterionResult
    goal_and_how: CriterionResult
    names_capability: CriterionResult
    need_not_want: CriterionResult
    success_condition: CriterionResult


class SSONEvaluation(BaseModel):
    criteria: SSONCriteria
    feedback: str = Field(
        description="Under 120 words, for the engineer: what is strong and what the PRD "
        "would need to say to make the SSON stronger."
    )
