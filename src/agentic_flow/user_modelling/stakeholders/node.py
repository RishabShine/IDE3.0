import json

from langchain_core.messages import HumanMessage, SystemMessage

from agentic_flow.core.models import base_model
from agentic_flow.state import AgentState
from agentic_flow.user_modelling.stakeholders import prompt
from agentic_flow.user_modelling.stakeholders.schema import (
    StakeHolder,
    StakeHolderResponse,
)


stakeholder_extractor = base_model.with_structured_output(
    StakeHolderResponse, method="json_schema"
)


def prepare_stakeholder_request(state: AgentState) -> AgentState:
    """Prepare the PRD and intent context for a single extraction call."""
    prd = state.get("prd", "")
    if not isinstance(prd, str) or not prd.strip():
        raise ValueError("A non-empty PRD is required for stakeholder extraction.")

    #! REPLACE WITH ACTUAL INTENT DATA WHEN MERGED
    intent_context = {}
    instructions = prompt.STAKEHOLDER_EXTRACTION_PROMPT.format(
        prd=prd,
        intent_context=json.dumps(intent_context, ensure_ascii=False),
    )
    return {"stakeholder_metadata": {"instructions": instructions, "stakeholders": []}}


def extract_stakeholders(state: AgentState) -> AgentState:
    """Extract stakeholder details, assign string IDs, and store the records."""
    metadata = state["stakeholder_metadata"]
    response = StakeHolderResponse.model_validate(
        stakeholder_extractor.invoke([
            SystemMessage(content=prompt.STAKEHOLDER_EXTRACTION_INSTRUCTIONS),
            HumanMessage(content=metadata["instructions"]),
        ])
    )
    stakeholders = [
        StakeHolder(stakeholder_id=f"Stakeholder-{number}", **item.model_dump()).model_dump()
        for number, item in enumerate(response.stakeholders, start=1)
    ]
    return {"stakeholder_metadata": {**metadata, "stakeholders": stakeholders}}
