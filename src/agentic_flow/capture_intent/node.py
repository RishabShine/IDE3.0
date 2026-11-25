from langchain_core.messages import HumanMessage, SystemMessage

from agentic_flow.capture_intent import prompts
from agentic_flow.capture_intent.schema import CapturedIntentResponse
from agentic_flow.core.models import base_model
from agentic_flow.state import AgentState

# Allow room for the PRD and the structured intent payload.
intent_extractor = (
    base_model.model_copy(update={"num_ctx": 16384})
    .with_structured_output(CapturedIntentResponse, method="json_schema")
)


def prepare_intent_request(state: AgentState) -> AgentState:
    """Prepare the PRD for a single intent-extraction call."""
    prd = state.get("prd", "")
    if not isinstance(prd, str) or not prd.strip():
        raise ValueError("A non-empty PRD is required for intent extraction.")

    instructions = prompts.INTENT_EXTRACTION_PROMPT.format(prd=prd)
    return {
        "intent_metadata": {
            "single_statement_intent": "",
            "evaluation_of_statement": "not_met",
            "evaluation_of_statement_feedback": "",
            "attempt_number": 0,
            "instructions": instructions,
        }
    }


def _assign_problem_ids(problems: list[dict]) -> list[dict]:
    records = []
    for number, item in enumerate(problems, start=1):
        records.append({
            "id": f"Problem-{number}",
            "description": item["description"].strip(),
            "source": (item.get("source") or "").strip(),
        })
    return records


def _assign_benefit_ids(benefits: list[dict], problem_count: int) -> list[dict]:
    records = []
    for number, item in enumerate(benefits, start=1):
        addresses = []
        for index in item.get("addresses") or []:
            if isinstance(index, int) and 1 <= index <= problem_count:
                addresses.append(f"Problem-{index}")
        records.append({
            "id": f"Benefit-{number}",
            "description": item["description"].strip(),
            "source": (item.get("source") or "").strip(),
            "addresses": addresses,
            "measure": (item.get("measure") or "").strip(),
            "kind": item.get("kind"),
        })
    return records


def extract_intent(state: AgentState) -> AgentState:
    """Extract intent from the PRD, assign problem/benefit IDs, and store both snapshots."""
    metadata = state["intent_metadata"]
    messages = [
        SystemMessage(content=prompts.INTENT_EXTRACTION_INSTRUCTIONS),
        HumanMessage(content=metadata["instructions"]),
    ]
    response = CapturedIntentResponse.model_validate(intent_extractor.invoke(messages))
    intent = response.intent.model_dump()

    problems = _assign_problem_ids(intent["problems"])
    benefits = _assign_benefit_ids(intent["benefits"], len(problems))
    goals = [goal.strip() for goal in intent.get("goals") or [] if str(goal).strip()]
    statement = " ".join(intent["single_statement_intent"].split())

    captured = {
        "single_statement_intent": statement,
        "what": " ".join(intent.get("what", "").split()),
        "how": " ".join(intent.get("how", "").split()),
        "why": " ".join(intent.get("why", "").split()),
        "success_measure": " ".join(intent.get("success_measure", "").split()),
        "current_process": " ".join(intent.get("current_process", "").split()),
        "problems": problems,
        "benefits": benefits,
        "goals": goals,
    }

    # Keep intent_metadata compatible with older readers; mark as derived, not reviewed.
    return {
        "intent_metadata": {
            "single_statement_intent": statement,
            "evaluation_of_statement": "met",
            "evaluation_of_statement_feedback": (
                "Derived from the PRD in one pass (no interactive SSON review)."
            ),
            "attempt_number": 1,
        },
        "captured_intent": captured,
    }
