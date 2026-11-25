from typing import Literal

from pydantic import BaseModel, Field


class ProblemData(BaseModel):
    """A current problem or pain point stated in the PRD."""

    description: str
    source: str = ""


class BenefitData(BaseModel):
    """An expected benefit or outcome stated in the PRD."""

    description: str
    source: str = ""
    # 1-based indexes into the problems list in the same response.
    addresses: list[int] = Field(default_factory=list)
    measure: str = ""
    kind: Literal["hard", "soft"] | None = None


class CapturedIntentData(BaseModel):
    """Intent artifacts extracted from the PRD, without assigned problem/benefit IDs."""

    single_statement_intent: str
    what: str = ""
    how: str = ""
    why: str = ""
    success_measure: str = ""
    current_process: str = ""
    problems: list[ProblemData] = Field(default_factory=list)
    benefits: list[BenefitData] = Field(default_factory=list)
    # High-level goal statements taken from the PRD (not the later goals subgraph).
    goals: list[str] = Field(default_factory=list)


class CapturedIntentResponse(BaseModel):
    intent: CapturedIntentData
