from typing import Literal

from pydantic import BaseModel, Field

InvestCriterion = Literal[
    "independent", "negotiable", "valuable", "estimable", "small", "testable"
]


# generation: one call per extracted goal
# -----------------------------------------------------------------------------

class GeneratedStory(BaseModel):
    actor: str = Field(description="The goal actor (by name) who wants this.")
    action: str = Field(description="What the actor wants to do; starts with a verb.")
    expected_outcome: str = Field(description="The value the actor gets, toward the goal.")


class StoryList(BaseModel):
    stories: list[GeneratedStory]


# revision: explicit operations, so untouched stories keep their IDs
# -----------------------------------------------------------------------------
# A null id means a new story. The node, not the model, assigns new IDs.

class StoryUpdate(BaseModel):
    id: str | None
    parent_id: str = Field(description="The ID of the goal the story belongs to.")
    actor: str
    action: str
    expected_outcome: str


class StoryRevision(BaseModel):
    updates: list[StoryUpdate]
    removed_ids: list[str]
    clarification_feedback: str


# INVEST check (3RA3 L24), one call per story
# -----------------------------------------------------------------------------

class InvestCheck(BaseModel):
    failed_criteria: list[InvestCriterion]
    feedback: str
    open_questions: list[str] = Field(
        description="Questions for the engineer that would make the story testable."
    )
