"""What the model returns for the use case model (3RA3 L13).

The model refers to actors and use cases by name; code assigns the IDs,
resolves every reference and checks the links (see node.py).
"""
from typing import Literal

from pydantic import BaseModel, Field


class ExtractedActor(BaseModel):
    name: str = Field(description="The actor as the PRD names it, e.g. 'Student' or "
                      "'MacID sign-in service'. Always outside the system.")
    kind: Literal["human", "system", "organization"] = Field(
        description="human: a person or role; system: another software system, device "
        "or service; organization: an institution or company.")
    stakeholder_id: str | None = Field(
        description="The ID of the supplied stakeholder this actor is, copied exactly. "
        "Null for an actor that is no supplied stakeholder, e.g. an external system.")


class ExtractedUseCase(BaseModel):
    name: str = Field(description="An infinitive verb phrase naming the primary actor's "
                      "goal, e.g. 'Book pickup slot'. Not a step, screen or feature list.")
    description: str = Field(description="One sentence: what the primary actor achieves "
                             "with the system.")
    primary_actor: str = Field(description="The name of the actor whose goal this use "
                               "case meets, copied from the actors list.")
    supporting_actors: list[str] = Field(
        description="Names of the other actors whose participation is needed, copied "
        "from the actors list. Empty if none.")
    goal_ids: list[str] = Field(
        description="IDs of the supplied goals (e.g. 'Goal-2') this use case helps "
        "achieve. Empty if none clearly applies.")


class ExtractedRelationship(BaseModel):
    kind: Literal["include", "extend"]
    source: str = Field(description="include: the base use case's name. extend: the "
                        "extending use case's name.")
    target: str = Field(description="include: the included use case's name. extend: "
                        "the base use case's name it extends.")
    condition: str = Field(description="extend: when the extension applies, e.g. 'if "
                           "the slot is full'. include: an empty string.")


class UseCaseModelResponse(BaseModel):
    system_name: str = Field(description="A short name for the system under design, "
                             "drawn as the system boundary.")
    actors: list[ExtractedActor]
    use_cases: list[ExtractedUseCase]
    relationships: list[ExtractedRelationship] = Field(
        description="Only include/extend links the PRD clearly supports. Use an empty "
        "list when there are none; most rough models need few or none.")
