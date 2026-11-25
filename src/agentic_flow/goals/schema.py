from typing import Literal

from pydantic import BaseModel, Field


class GoalActor(BaseModel):
    """An actor's involvement in a goal; actors may include subsystems."""

    name: str = Field(
        description="The actor named or described in the PRD. Keep its name even when "
        "no stakeholder link exists."
    )
    stakeholder_id: str | None = Field(
        description="An existing stakeholder ID when the actor clearly corresponds to "
        "that stakeholder. Use null for an unmatched actor or subsystem; do not "
        "invent a stakeholder or force a relationship."
    )
    role: str = Field(
        description="The role this actor assumes in pursuing this goal, as supplied "
        "in the PRD. Use an empty string if unspecified."
    )
    involvement: str = Field(
        description="What this actor seeks or contributes in relation to this specific "
        "goal, based on the PRD. Describe its perspective or contribution, not "
        "a plan of actions. Use an empty string if unspecified."
    )


class GoalData(BaseModel):
    """Goal information extracted from the PRD, without refinement or an ID."""

    statement: str = Field(
        description="The desired outcome or stakeholder objective expressed in the PRD. "
        "Preserve its scope and any supplied targets; do not decompose it or "
        "invent satisfaction criteria."
    )
    actors: list[GoalActor] = Field(
        description="The people, groups, or subsystems described as acting to achieve "
        "this goal. Use an empty list if none are established."
    )
    goal_type: Literal["hard", "soft"] | None = Field(
        description="Hard when satisfaction is well defined; soft for a desired quality "
        "whose satisfaction is not fully defined. Classify using the supplied "
        "description, without adding measurements. Use null if unclear."
    )
    resources: list[str] = Field(
        description="Resources the PRD identifies as used by actors to achieve this "
        "goal. Use an empty list if unspecified; do not propose resources."
    )
    plans: str = Field(
        description="The supplied description of how actors will act to achieve the "
        "goal. Use an empty string if absent; do not devise a plan or add steps."
    )
    justification: str = Field(
        description="The supplied rationale for why this goal matters, including "
        "problems or benefits it addresses when stated. Use an empty string if "
        "absent. Do not evaluate feasibility or invent a reason for the goal."
    )


class Goal(GoalData):
    """Stored goal with an application-assigned ID such as Goal-1."""

    goal_id: str


class GoalResponse(BaseModel):
    goals: list[GoalData]
