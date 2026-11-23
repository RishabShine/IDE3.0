from typing import Literal

from pydantic import BaseModel


class StakeHolderData(BaseModel):
    """Stakeholder details extracted by the model, without an application ID."""

    name: str
    involvement: Literal["direct", "indirect"] | None
    summary: str
    justification: str


class StakeHolder(StakeHolderData):
    """Stored stakeholder with an application-assigned ID such as Stakeholder-1."""

    stakeholder_id: str


class StakeHolderResponse(BaseModel):
    stakeholders: list[StakeHolderData]
