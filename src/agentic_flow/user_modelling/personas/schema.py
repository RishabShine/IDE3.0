from pydantic import BaseModel, Field


class PersonaData(BaseModel):
    """PRD-extracted persona details using the 3RA3 Lecture 06 MSF template."""

    stakeholder_id: str | None = Field(
        description="The exact ID of the supplied stakeholder representing this persona's "
        "user group, matched using its name and summary. Use null if the relationship "
        "is missing or ambiguous."
    )
    name: str = Field(
        description="The persona's supplied name, or an empty string if none is provided. "
        "Do not invent a name to complete the template."
    )
    role: str = Field(
        description="The user group this persona represents, as described in the PRD. "
        "Use an empty string if the group is unspecified."
    )
    status_and_trust_level: str = Field(
        description="Explicitly supplied favoured/disfavoured status and credentials. "
        "Use an empty string if unspecified. User status alone establishes neither."
    )
    # Demographics are optional in the lecture template; do not invent them.
    demographics: str = Field(
        description="Supplied age and personal details, or an empty string if absent."
    )
    ksa: str = Field(
        description="Supplied knowledge, skills, abilities, and capability limitations: "
        "what the person knows or can do. Preserve stated lack of knowledge. "
        "Usage times and routine activities belong in usage_patterns. Empty if absent."
    )
    gmc: str = Field(
        description="Supplied goals, motives, and concerns: desired outcomes, reasons, "
        "and worries. Keep these even if stakeholder_id is null. Empty if absent."
    )
    usage_patterns: str = Field(
        description="Supplied system-use frequency, activities, context, devices, and "
        "situational challenges: when, where, and how the person uses the system. "
        "Keep capabilities in ksa and desired outcomes in gmc. Empty if absent."
    )


class Persona(PersonaData):
    """Stored persona with an application-assigned ID such as Persona-1."""

    persona_id: str


class PersonaResponse(BaseModel):
    personas: list[PersonaData]
