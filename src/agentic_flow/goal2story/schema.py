from typing import Literal

from pydantic import BaseModel, Field

InvestCriterion = Literal[
    "independent", "negotiable", "valuable", "estimable", "small", "testable"
]


# goal extraction: PRD mode only (an IDE3.0 addition)
# -----------------------------------------------------------------------------

class ExtractedGoal(BaseModel):
    evidence: str = Field(
        default="", description="The PRD sentence the goal comes from, copied word for word."
    )
    goal: str = Field(description="One measurable business goal stated or implied by the PRD.")


# generation: one call per parent, following Goal2Story (arXiv:2503.13279, §3)
# -----------------------------------------------------------------------------

class GeneratedActor(BaseModel):
    name: str = Field(description="The actor group, e.g. 'Student'.")
    description: str = Field(description="Who they are and how they affect the goal.")
    stakeholder: str = Field(description="The confirmed stakeholder this actor comes from.")


class ActorList(BaseModel):
    actors: list[GeneratedActor]


class GeneratedImpact(BaseModel):
    description: str = Field(description="The change in the actor's behaviour.")


class ImpactList(BaseModel):
    impacts: list[GeneratedImpact]


class GeneratedDeliverable(BaseModel):
    description: str = Field(description="The software capability that supports the impact.")


class DeliverableList(BaseModel):
    deliverables: list[GeneratedDeliverable]


class GeneratedStory(BaseModel):
    actor: str
    action: str = Field(description="What the actor wants to do; starts with a verb.")
    expected_outcome: str = Field(description="The value the actor gets.")


# revision: explicit operations, so untouched items keep their IDs
# -----------------------------------------------------------------------------
# A null id means a new item. The node, not the model, assigns new IDs.

class ActorUpdate(BaseModel):
    id: str | None
    name: str
    description: str
    stakeholder: str


class ImpactUpdate(BaseModel):
    id: str | None
    parent_id: str
    description: str


class DeliverableUpdate(BaseModel):
    id: str | None
    parent_id: str
    description: str


class StoryUpdate(BaseModel):
    id: str | None
    parent_id: str
    actor: str
    action: str
    expected_outcome: str


class ActorRevision(BaseModel):
    updates: list[ActorUpdate]
    removed_ids: list[str]
    clarification_feedback: str


class ImpactRevision(BaseModel):
    updates: list[ImpactUpdate]
    removed_ids: list[str]
    clarification_feedback: str


class DeliverableRevision(BaseModel):
    updates: list[DeliverableUpdate]
    removed_ids: list[str]
    clarification_feedback: str


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
