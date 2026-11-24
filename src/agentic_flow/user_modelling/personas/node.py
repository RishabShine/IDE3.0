import json

from langchain_core.messages import HumanMessage, SystemMessage

from agentic_flow.core.models import base_model
from agentic_flow.state import AgentState
from agentic_flow.user_modelling.personas import prompt
from agentic_flow.user_modelling.personas.schema import Persona, PersonaResponse


persona_extractor = base_model.with_structured_output(
    PersonaResponse, method="json_schema"
)


def prepare_persona_request(state: AgentState) -> AgentState:
    """Prepare the PRD and current project understanding for persona extraction."""
    prd = state.get("prd", "")
    if not isinstance(prd, str) or not prd.strip():
        raise ValueError("A non-empty PRD is required for persona extraction.")

    stakeholders = state.get("stakeholder_metadata", {}).get("stakeholders", [])
    #! CONNECT TO ACTUAL INTENT OUTPUT WHEN MERGED; accepts a supplied snapshot for now.
    intent_context = state.get("captured_intent", {})
    instructions = prompt.PERSONA_EXTRACTION_PROMPT.format(
        prd=prd,
        stakeholders=json.dumps(stakeholders, ensure_ascii=False),
        intent_context=json.dumps(intent_context, ensure_ascii=False),
    )
    return {"persona_metadata": {"instructions": instructions, "personas": []}}


def extract_personas(state: AgentState) -> AgentState:
    """Extract persona details and store IDs without forcing stakeholder links."""
    metadata = state["persona_metadata"]
    response = PersonaResponse.model_validate(
        persona_extractor.invoke([
            SystemMessage(content=prompt.PERSONA_EXTRACTION_INSTRUCTIONS),
            HumanMessage(content=metadata["instructions"]),
        ])
    )
    stakeholder_ids = {
        item["stakeholder_id"]
        for item in state.get("stakeholder_metadata", {}).get("stakeholders", [])
    }
    personas = []
    for number, item in enumerate(response.personas, start=1):
        record = Persona(persona_id=f"Persona-{number}", **item.model_dump()).model_dump()
        if record["stakeholder_id"] not in stakeholder_ids:
            record["stakeholder_id"] = None
        personas.append(record)

    return {"persona_metadata": {**metadata, "personas": personas}}
