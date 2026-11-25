"""What the model returns. It never returns IDs: code numbers the items, checks each
source quote against the PRD and validates every link (see node.py)."""
from pydantic import BaseModel, Field

SOURCE = "The exact PRD words this item comes from, copied character for character."


class ExtractedItem(BaseModel):
    description: str
    source: str = Field(description=SOURCE)


# G.2 Current situation
# -----------------------------------------------------------------------------

class ExtractedProblem(BaseModel):
    description: str = Field(
        description="What goes wrong today, for whom, and why it matters, in the PRD's words."
    )
    source: str = Field(description=SOURCE)


class CurrentSituationExtraction(BaseModel):
    current_situation: str = Field(
        description="How the process works today in 1-3 sentences: who does what, with "
        "which tools or systems. No problems or judgments. Empty string if absent."
    )
    problems: list[ExtractedProblem]


# G.3 Expected benefits
# -----------------------------------------------------------------------------

class ExtractedBenefit(BaseModel):
    description: str = Field(
        description="What improves, or what new process becomes possible, and for whom."
    )
    source: str = Field(description=SOURCE)
    addresses: list[str] = Field(description="IDs of the problems it fixes, e.g. ['Problem-1'].")
    measure: str | None = Field(
        description="The complete target phrase from the PRD that shows the benefit was "
        "reached, e.g. 'within one minute of booking'. Null if the PRD gives none."
    )


class OutOfScopeProblem(BaseModel):
    problem_id: str = Field(description="ID of a listed problem, e.g. 'Problem-2'.")
    source: str = Field(
        description="The exact PRD words saying this project will not address that "
        "problem, copied character for character."
    )


class ExpectedBenefitsExtraction(BaseModel):
    benefits: list[ExtractedBenefit]
    out_of_scope_problems: list[OutOfScopeProblem] = Field(
        description="Problems the PRD explicitly says this project will not address."
    )


# E.5 Effects, E.6 Invariants, constraints and scope exclusions
# -----------------------------------------------------------------------------

class EnvironmentExtraction(BaseModel):
    effects: list[ExtractedItem]
    invariants: list[ExtractedItem]
    constraints: list[ExtractedItem]
    scope_exclusions: list[ExtractedItem]
