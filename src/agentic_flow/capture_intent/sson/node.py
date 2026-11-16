from langchain_core.messages import HumanMessage, SystemMessage

from agentic_flow.capture_intent.sson.prompts import (
    SINGLE_STATEMENT_OF_NEED_STARTER_PROMPT,
    SINGLE_STATEMENT_OF_NEED_EVALUATION_PROMPT,
)
from agentic_flow.capture_intent.sson.schema import SSONEvaluation
from agentic_flow.core.models import base_model
from agentic_flow.core.shared_nodes import get_user_input
from agentic_flow.state import AgentState

sson_evaluator = base_model.with_structured_output(SSONEvaluation)

POINTS = {"met": 1.0, "partially_met": 0.5, "not_met": 0.0}
PASS_THRESHOLD = 80


def capture_sson(state: AgentState) -> AgentState:
    """
    Ask the user for their Single Statement of Need. Shows the starter prompt
    (definition + examples) on the first attempt, and the previous attempt's
    evaluation feedback on every retry.
    """
    intent_metadata = state.get("intent_metadata", {})
    statement = get_user_input(
        intent_metadata.get("feedback") or SINGLE_STATEMENT_OF_NEED_STARTER_PROMPT
    )
    return {"intent_metadata": {**intent_metadata, "single_statement_intent": statement}}


def evaluate_sson(state: AgentState) -> AgentState:
    """
    Grade the SSON against the L04 criteria. The LLM gives a verdict per
    criterion; the score and the pass/fail decision are computed here.
    """
    intent_metadata = state["intent_metadata"]
    statement = intent_metadata["single_statement_intent"]
    attempt_number = intent_metadata.get("attempt_number", 0) + 1

    evaluation = sson_evaluator.invoke(
        [
            SystemMessage(
                content=SINGLE_STATEMENT_OF_NEED_EVALUATION_PROMPT.format(
                    project_context=state.get("project_context", ""),
                    attempt_number=attempt_number,
                )
            ),
            HumanMessage(content=f"<statement>{statement}</statement>"),
        ]
    )

    verdicts = [c["verdict"] for c in evaluation.criteria.model_dump().values()]
    score = round(100 * sum(POINTS[v] for v in verdicts) / len(verdicts))
    feedback = evaluation.feedback_to_user
    if evaluation.suggested_revision:
        feedback += f"\n\n**Suggested revision:** {evaluation.suggested_revision}"

    return {
        "intent_metadata": {
            "single_statement_intent": statement,
            "what": evaluation.what,
            "how": evaluation.how,
            "why": evaluation.why,
            "success_measure": evaluation.success_measure,
            "evaluation_score": score,
            "passed": evaluation.is_sson_attempt
            and score >= PASS_THRESHOLD
            and "not_met" not in verdicts,
            "feedback": feedback,
            "attempt_number": attempt_number,
        }
    }
