"""What the impact analysis model returns. Code checks every ID and field (node.py)."""
from typing import Literal

from pydantic import BaseModel, Field

NewArtifactType = Literal["problem", "benefit", "effect", "invariant", "constraint",
                          "scope_exclusion", "goal"]


class FieldChange(BaseModel):
    field: str = Field(description="One of the artifact's revisable fields, as listed.")
    value: str = Field(description="The complete new text for that field.")


class Assessment(BaseModel):
    artifact_id: str = Field(description="The candidate's ID, copied exactly.")
    verdict: Literal["unaffected", "revise", "obsolete"] = Field(
        description="unaffected: still correct after the change. revise: still needed "
        "but its text no longer fits. obsolete: it only existed because of what changed.")
    reason: str = Field(description="One sentence naming the change and why it does or "
                        "does not affect this artifact.")
    changes: list[FieldChange] = Field(
        default_factory=list,
        description="For revise only: the smallest field edits that make it consistent.")


class NewArtifact(BaseModel):
    type: NewArtifactType
    text: str = Field(description="The new artifact's description (a goal's statement).")
    reason: str = Field(description="Which change makes it necessary.")


class ImpactResponse(BaseModel):
    assessments: list[Assessment]
    new_artifacts: list[NewArtifact] = Field(
        default_factory=list,
        description="Only artifacts the change clearly requires and no candidate covers. "
        "Usually empty.")
