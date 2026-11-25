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
        description="A short descriptive phrase for the functional capacity this "
        "actor assumes for this goal: what kind of participant it is or what "
        "responsibility it has, supported by the PRD. This differs from its name "
        "(who it is) and involvement (what it seeks or contributes). Never use "
        "the stakeholder classifications direct or indirect. Use an empty string "
        "if its capacity is unspecified; do not invent responsibilities."
    )
    involvement: str = Field(
        description="A short sentence about THIS actor's interest in or contribution "
        "to THIS goal: what outcome it seeks or what part it plays in achieving it, "
        "as supplied in the PRD. This is not the input stakeholder's project-level "
        "direct/indirect classification; never copy that value here. A role label "
        "alone is also insufficient. Distinguish seeking or benefiting from an "
        "outcome from responsibility for delivering it. If no goal-specific "
        "interest or contribution "
        "is established, return an empty string rather than inventing one."
    )


class GoalData(BaseModel):
    """Goal information extracted from the PRD, without refinement or an ID."""

    statement: str = Field(
        description="The desired outcome or stakeholder objective expressed in the PRD. "
        "Include its scope, supplied targets, units, and satisfaction condition "
        "here, not solely in justification. Resolve references such as 'that time' "
        "so the objective stands alone; do not decompose it or "
        "invent satisfaction criteria."
    )
    actors: list[GoalActor] = Field(
        description="The people, groups, or subsystems described as acting to achieve "
        "or seeking this goal. Include contributors established by its supplied "
        "approach, including participants assigned actions even if they do not "
        "state the objective themselves, not just its first named stakeholder. "
        "Use an empty list if none are established."
    )
    goal_type: Literal["hard", "soft"] | None = Field(
        description="Hard for a desired outcome with a definite achievement condition "
        "in the PRD; numbers are not required. Soft for a qualitative objective "
        "whose satisfaction depends on undefined judgement, including when the PRD "
        "explicitly says no satisfaction definition is agreed. A plan or actor "
        "does not make a quality hard. Classify this statement's outcome: a definite "
        "capability stays hard even if its purpose is reassurance; a separate "
        "undefined quality stays soft. Do not invent criteria. Use null if unclear."
    )
    resources: list[str] = Field(
        description="Resources the PRD identifies as used by actors to achieve this "
        "goal, including records, information, or tools in its supplied approach. "
        "Include things its actors read, update, consult, or exchange, even when "
        "also mentioned in plans. Name the things used, not the actions. "
        "Use an empty list if unspecified; do not propose resources."
    )
    plans: str = Field(
        description="The supplied description of how actors will act to achieve the "
        "goal, retaining who does what and the supplied mechanism supporting "
        "the objective, rather than a generic system workflow. Use an empty string "
        "if absent or explicitly not agreed; a statement that no plan exists is "
        "not a plan. Do not devise a plan or add steps."
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
