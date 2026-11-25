import json

from langchain_core.messages import HumanMessage, SystemMessage

from agentic_flow.capture_intent.common import checked_source, flag, unflag
from agentic_flow.core.models import base_model
from agentic_flow.goals import prompt
from agentic_flow.goals.schema import Goal, GoalResponse
from agentic_flow.state import AgentState


# Allow room for the PRD, upstream context, instructions, and generated goals.
# Keep the larger context window specific to this extraction stage.
goal_extractor = (
    base_model.model_copy(update={"num_ctx": 16384})
    .with_structured_output(GoalResponse, method="json_schema")
)


def _pick(items, keys) -> list[dict]:
    return [{k: (unflag(i.get(k)) if k == "description" else i.get(k)) for k in keys}
            for i in items or []]


def intent_context(captured: dict | None) -> dict:
    """The parts of the captured intent goal extraction reads, with their IDs.

    The whole record would add the SSON evaluation and current situation, which
    say nothing about goals; benefit IDs are what goals link to.
    """
    captured = captured or {}
    context = {
        "single_statement_of_need": unflag(captured.get("single_statement_intent")),
        "context_and_objective": captured.get("context_and_objective"),
        "success_measure": captured.get("success_measure"),
        "problems": _pick(captured.get("problems"), ("id", "description")),
        "benefits": _pick(captured.get("benefits"), ("id", "description", "addresses", "measure")),
        "constraints": _pick(captured.get("constraints"), ("id", "description")),
        "scope_exclusions": _pick(captured.get("scope_exclusions"), ("id", "description")),
    }
    return {k: v for k, v in context.items() if v}


def prepare_goal_request(state: AgentState) -> AgentState:
    """Prepare the PRD and current project understanding for goal extraction."""
    prd = state.get("prd", "")
    if not isinstance(prd, str) or not prd.strip():
        raise ValueError("A non-empty PRD is required for goal extraction.")

    stakeholders = state.get("stakeholder_metadata", {}).get("stakeholders", [])
    personas = state.get("persona_metadata", {}).get("personas", [])
    instructions = prompt.GOAL_EXTRACTION_PROMPT.format(
        prd=prd,
        intent_context=json.dumps(intent_context(state.get("captured_intent")),
                                  ensure_ascii=False),
        stakeholders=json.dumps(stakeholders, ensure_ascii=False),
        personas=json.dumps(personas, ensure_ascii=False),
    )
    return {"goal_metadata": {"instructions": instructions, "goals": []}}


def extract_goals(state: AgentState) -> AgentState:
    """Extract goals, assign string IDs, and check every link and quote in code.

    A goal whose quote is not in the PRD is kept but red-flagged, like the
    captured intent. Links to unknown stakeholders become null; links to
    unknown benefits are dropped.
    """
    metadata = state["goal_metadata"]
    prd = state.get("prd", "")
    messages = [
        SystemMessage(content=prompt.GOAL_EXTRACTION_INSTRUCTIONS),
        HumanMessage(content=metadata["instructions"]),
    ]
    response = GoalResponse.model_validate(goal_extractor.invoke(messages))
    stakeholder_ids = {
        item["stakeholder_id"]
        for item in state.get("stakeholder_metadata", {}).get("stakeholders", [])
    }
    benefit_ids = {b["id"] for b in (state.get("captured_intent") or {}).get("benefits") or []}
    goals = []
    for item in response.goals:
        statement = " ".join(item.statement.split())
        if not statement:
            continue
        record = Goal(goal_id=f"Goal-{len(goals) + 1}", **item.model_dump()).model_dump()
        source = checked_source(record["source"] or None, statement, prd)
        record["statement"] = statement if source else flag(statement)
        record["source"] = source
        record["benefit_ids"] = [b for b in dict.fromkeys(record["benefit_ids"])
                                 if b in benefit_ids]
        for actor in record["actors"]:
            if actor["stakeholder_id"] not in stakeholder_ids:
                actor["stakeholder_id"] = None
        goals.append(record)

    return {"goal_metadata": {**metadata, "goals": goals}}
