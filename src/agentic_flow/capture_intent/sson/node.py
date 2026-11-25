from langchain_core.messages import HumanMessage, SystemMessage

from agentic_flow.capture_intent.common import flag, intent, require_prd, traced, unflag
from agentic_flow.capture_intent.sson import prompts
from agentic_flow.capture_intent.sson.schema import SSONEvaluation, SSONExtraction
from agentic_flow.core.models import base_model
from agentic_flow.state import AgentState

sson_extractor = base_model.with_structured_output(SSONExtraction, method="json_schema")
sson_evaluator = base_model.with_structured_output(SSONEvaluation, method="json_schema")

POINTS = {"met": 1.0, "partially_met": 0.5, "not_met": 0.0}
PASS_THRESHOLD = 80


def _text(value: str | None) -> str | None:
    value = " ".join((value or "").split())
    return value or None


def extract_sson(state: AgentState) -> AgentState:
    """Derive the SSON and G.1 context from the PRD.

    An SSON the PRD states word for word is used as is. Otherwise the model's
    synthesized SSON is used and starts with a red flag, so the engineer can see
    it was derived rather than supplied.
    """
    prd = require_prd(state)
    result = SSONExtraction.model_validate(sson_extractor.invoke([
        SystemMessage(content=prompts.SSON_EXTRACTION_INSTRUCTIONS),
        HumanMessage(content=prompts.SSON_EXTRACTION_PROMPT.format(prd=prd)),
    ]))

    stated = _text(result.stated_sson)
    if stated and traced(stated, prd):
        sson, source = stated, "stated"
    else:
        sson, source = flag(_text(result.synthesized_sson) or ""), "synthesized"

    return {"captured_intent": {
        **intent(state),
        "single_statement_intent": sson,
        "sson_source": source,
        "sson_evidence": [q.strip() for q in result.evidence if traced(q, prd)],
        "what": _text(result.what),
        "how": _text(result.how),
        "why": _text(result.why),
        "success_measure": _text(result.success_measure),
        "context_and_objective": _text(result.context_and_objective) or "",
    }}


def evaluate_sson(state: AgentState) -> AgentState:
    """Grade the SSON against the L04 criteria. Non-blocking: the result is only reported."""
    captured = intent(state)
    evaluation = SSONEvaluation.model_validate(sson_evaluator.invoke([
        SystemMessage(content=prompts.SSON_EVALUATION_INSTRUCTIONS),
        HumanMessage(content=prompts.SSON_EVALUATION_PROMPT.format(
            prd=require_prd(state),
            source=("synthesized from the PRD" if captured.get("sson_source") == "synthesized"
                    else "stated in the PRD"),
            sson=unflag(captured.get("single_statement_intent")),
        )),
    ]))

    criteria = evaluation.criteria.model_dump()
    verdicts = [c["verdict"] for c in criteria.values()]
    score = round(100 * sum(POINTS[v] for v in verdicts) / len(verdicts))
    return {"captured_intent": {
        **captured,
        "sson_evaluation": {
            "criteria": criteria,
            "score": score,
            "passed": score >= PASS_THRESHOLD and "not_met" not in verdicts,
            "feedback": evaluation.feedback.strip(),
        },
    }}
