from agentic_flow.core.shared_nodes import get_user_input
from agentic_flow.prd_intake.prompts import PRD_INTAKE_PROMPT
from agentic_flow.state import AgentState


def intake_prd(state: AgentState) -> AgentState:
    """Collect the raw PRD text without extracting or evaluating artifacts."""
    prd = get_user_input(prompt=PRD_INTAKE_PROMPT)
    return {"prd": prd}
