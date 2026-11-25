from typing import Any, Literal, TypedDict

ArtifactType = Literal["intent", "problem", "benefit", "stakeholder", "persona"]

# Edges point from the lower-level artifact to the higher-level one it traces to.
Relation = Literal[
    "motivates",       # Problem -> Intent
    "realizes",        # Benefit -> Intent
    "addresses",       # Benefit -> Problem
    "concerned_with",  # Stakeholder -> Intent
    "represents",      # Persona -> Stakeholder
]

GapKind = Literal[
    "missing_artifacts",            # an artifact type with nothing extracted
    "duplicate_id",                 # two artifacts share an ID; the later one is dropped
    "dangling_link",                # a link names an artifact that does not exist
    "unlinked_persona",             # persona with no stakeholder
    "stakeholder_without_persona",  # direct stakeholder no persona represents
    "unaddressed_problem",          # problem no benefit addresses
]


class ArtifactNode(TypedDict):
    id: str
    type: ArtifactType
    label: str
    # the artifact's own fields, as the extraction step stored them
    data: dict[str, Any]


class ArtifactEdge(TypedDict):
    source: str
    target: str
    relation: Relation


class ArtifactGap(TypedDict):
    kind: GapKind
    artifact_id: str | None
    detail: str


class ArtifactGraph(TypedDict):
    nodes: list[ArtifactNode]
    edges: list[ArtifactEdge]
    gaps: list[ArtifactGap]
