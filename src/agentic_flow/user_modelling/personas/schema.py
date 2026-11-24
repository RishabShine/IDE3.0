from pydantic import BaseModel, Field


class PersonaData(BaseModel):
    """PRD-extracted persona details using the 3RA3 Lecture 06 MSF template."""

    stakeholder_id: str | None = Field(
        description="Copy an existing stakeholder ID only when the supplied information "
        "clearly supports the relationship. Use null when no clear match exists; "
        "do not invent a stakeholder or force a link."
    )
    name: str = Field(
        description="The persona's supplied name, or an empty string if none is provided. "
        "Do not invent a name to complete the template."
    )
    role: str = Field(description="The user group represented by this persona.")
    status_and_trust_level: str = Field(
        description="Supplied favoured/disfavoured status and level of credentials. "
        "Use an empty string when not established."
    )
    # Demographics are optional in the lecture template; do not invent them.
    demographics: str = Field(
        description="Supplied age and personal details, or an empty string if absent."
    )
    ksa: str = Field(
        description="Knowledge, skills, and abilities supported by the supplied information. "
        "Use an empty string if absent."
    )
    gmc: str = Field(
        description="Goals, motives, and concerns supported by the supplied information. "
        "Use an empty string if absent."
    )
    usage_patterns: str = Field(
        description="Supplied frequency, typical system use, and usage challenges. "
        "Use an empty string if absent."
    )


class Persona(PersonaData):
    """Stored persona with an application-assigned ID such as Persona-1."""

    persona_id: str


class PersonaResponse(BaseModel):
    personas: list[PersonaData]
