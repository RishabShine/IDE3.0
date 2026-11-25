import json

from langchain_core.messages import HumanMessage, SystemMessage

from agentic_flow.core.models import base_model
from agentic_flow.goals import prompt
from agentic_flow.goals.schema import Goal, GoalResponse
from agentic_flow.state import AgentState


goal_extractor = base_model.with_structured_output(
    GoalResponse, method="json_schema"
)


def prepare_goal_request(state: AgentState) -> AgentState:
    """Prepare the PRD and current project understanding for goal extraction."""
    prd = state.get("prd", "")
    if not isinstance(prd, str) or not prd.strip():
        raise ValueError("A non-empty PRD is required for goal extraction.")

    #! CONNECT TO ACTUAL INTENT OUTPUT WHEN MERGED; accepts a supplied snapshot for now.
    intent_context = state.get("captured_intent", {})
    stakeholders = state.get("stakeholder_metadata", {}).get("stakeholders", [])
    personas = state.get("persona_metadata", {}).get("personas", [])
    instructions = prompt.GOAL_EXTRACTION_PROMPT.format(
        prd=prd,
        intent_context=json.dumps(intent_context, ensure_ascii=False),
        stakeholders=json.dumps(stakeholders, ensure_ascii=False),
        personas=json.dumps(personas, ensure_ascii=False),
    )
    return {"goal_metadata": {"instructions": instructions, "goals": []}}


def extract_goals(state: AgentState) -> AgentState:
    """Extract goals, assign string IDs, and retain actors with unresolved links."""
    metadata = state["goal_metadata"]
    response = GoalResponse.model_validate(
        goal_extractor.invoke([
            SystemMessage(content=prompt.GOAL_EXTRACTION_INSTRUCTIONS),
            HumanMessage(content=metadata["instructions"]),
        ])
    )
    stakeholder_ids = {
        item["stakeholder_id"]
        for item in state.get("stakeholder_metadata", {}).get("stakeholders", [])
    }
    goals = []
    for number, item in enumerate(response.goals, start=1):
        record = Goal(goal_id=f"Goal-{number}", **item.model_dump()).model_dump()
        for actor in record["actors"]:
            if actor["stakeholder_id"] not in stakeholder_ids:
                actor["stakeholder_id"] = None
        goals.append(record)

    return {"goal_metadata": {**metadata, "goals": goals}}
