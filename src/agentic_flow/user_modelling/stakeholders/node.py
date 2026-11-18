import json

from langchain_core.messages import HumanMessage, SystemMessage

from agentic_flow.core.models import base_model
from agentic_flow.core.validation import (
    ModelResponseError, check_coverage, check_operations, failed_metadata, invoke_checked,
)
from agentic_flow.core.shared_nodes import get_user_input
from agentic_flow.state import AgentState
from agentic_flow.user_modelling.stakeholders import prompt
from agentic_flow.user_modelling.stakeholders.schema import (
    StakeHolderDraft,
    StakeHolderEvaluation,
    StakeHolderResponse,
)


# JSON schema mode uses Ollama's structured output instead of tool calling.
stakeholder_evaluator = base_model.with_structured_output(
    StakeHolderEvaluation, method="json_schema"
)
stakeholder_response_processor = base_model.with_structured_output(
    StakeHolderResponse, method="json_schema"
)


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _turn_input(metadata) -> dict[str, str]:
    return {
        "user_feedback": metadata["latest_user_response"],
        "last_prompt_to_user": metadata["last_prompt_to_user"],
        "evaluation": _json(metadata["evaluation"]),
        "stakeholders": _json(metadata["drafts"]),
    }


def _collect_response(metadata, message: str) -> dict:
    # do not mutate state before interrupt(): this node restarts when resumed
    response = get_user_input(prompt=message)
    if not isinstance(response, str):
        raise ValueError("The stakeholder response must be text.")
    return {
        **metadata,
        "last_prompt_to_user": message,
        "latest_user_response": response,
        "user_confirmed": False,
        "approved_version": None,
    }


def _record(draft) -> str:
    return prompt.STAKEHOLDER_RECORD_TEMPLATE.format(
        **{**draft, "involvement": draft["involvement"] or "Not established"}
    )


def start_stakeholders(state: AgentState) -> AgentState:
    """Prepare reusable context and collect the first reply in a single node.

    Nothing is written before interrupt(). On resume, preparing the same local
    metadata again is safe; the node commits it together with the user's reply.
    """
    context = state.get("captured_intent", {})

    metadata = state.get("stakeholder_metadata")
    if not metadata or not metadata.get("initialized"):
        metadata = {
            "initialized": True,
            "initial_context_message": prompt.STAKEHOLDER_INTENT_CONTEXT_PROMPT.format(
                intent_context=_json(context)
            ),
            "last_prompt_to_user": "",
            "drafts": [],
            "next_draft_number": 1,
            "draft_version": 0,
            "evaluation": None,
            "evaluated_draft_version": None,
            "latest_user_response": "",
            "response_feedback": "",
            "model_error": None,
            "user_confirmed": False,
            "approved_version": None,
            "finalized_stakeholders": [],
        }
    metadata = _collect_response(
        metadata, prompt.STAKEHOLDER_STARTER_PROMPT
    )
    return {"stakeholder_metadata": metadata}


def process_stakeholder_response(state: AgentState) -> AgentState:
    """Interpret the reply, then apply user-requested additions, edits, and removals."""
    metadata = state["stakeholder_metadata"]
    if (metadata.get("model_error")
            and metadata["model_error"]["stage"] == "evaluation"
            and metadata["latest_user_response"].strip().upper() == "RETRY"):
        return {"stakeholder_metadata": {**metadata, "model_error": None, "response_feedback": ""}}
    request = prompt.STAKEHOLDER_RESPONSE_PROMPT.format(**_turn_input(metadata))
    # Each call gets reusable context, current records, and the latest exchange.
    # Older turns are not retained or replayed.
    messages = [
        SystemMessage(content=prompt.STAKEHOLDER_RESPONSE_INSTRUCTIONS),
        HumanMessage(content=metadata["initial_context_message"]),
        HumanMessage(content=request),
    ]
    drafts = {d["stakeholder_id"]: dict(d) for d in metadata["drafts"]}
    next_number = metadata["next_draft_number"]
    try:
        result = invoke_checked(
            stakeholder_response_processor, StakeHolderResponse, messages,
            lambda result: check_operations(result, drafts, "stakeholder_id", next_number),
        )
    except ModelResponseError as error:
        return {"stakeholder_metadata": failed_metadata(metadata, "response", error,
                                                     "finalized_stakeholders")}

    removed = result.removed_stakeholder_ids
    for stakeholder_id in removed:
        drafts.pop(stakeholder_id)

    for update in result.updates:
        stakeholder_id = update.stakeholder_id
        if stakeholder_id is None:
            stakeholder_id = f"Stakeholder-{next_number}"
            next_number += 1
        if not update.name.strip():
            raise ValueError("A stakeholder draft must have a name.")
        record = update.model_dump()
        record["stakeholder_id"] = stakeholder_id
        drafts[stakeholder_id] = StakeHolderDraft.model_validate(record).model_dump()

    current = list(drafts.values())
    return {
        "stakeholder_metadata": {
            **metadata,
            "drafts": current,
            "next_draft_number": next_number,
            "draft_version": metadata["draft_version"] + (current != metadata["drafts"]),
            # Keep the latest completed evaluation to interpret this reply.
            # Its version prevents using old verdicts to approve edited drafts.
            "response_feedback": result.clarification_feedback,
            "model_error": None,
            "user_confirmed": False,
            "approved_version": None,
            "finalized_stakeholders": [],
        }
    }


def evaluate_stakeholders(state: AgentState) -> AgentState:
    """Evaluate current drafts with reusable context and only the latest exchange."""
    metadata = state["stakeholder_metadata"]
    request = prompt.STAKEHOLDER_EVALUATION_PROMPT.format(**_turn_input(metadata))
    messages = [
        SystemMessage(content=prompt.STAKEHOLDER_EVALUATION_INSTRUCTIONS),
        HumanMessage(content=metadata["initial_context_message"]),
        HumanMessage(content=request),
    ]
    drafts = {d["stakeholder_id"]: d for d in metadata["drafts"]}

    def validate(result):
        check_coverage(result.provided_stakeholders, drafts, "stakeholder_id")
        for item in result.provided_stakeholders:
            related = item.overlap_stakeholder_ids
            if (not set(related).issubset(drafts) or item.stakeholder_id in related
                    or len(related) != len(set(related))):
                raise ValueError("Overlap IDs must refer to other current drafts exactly once.")

    try:
        result = invoke_checked(stakeholder_evaluator, StakeHolderEvaluation, messages, validate)
    except ModelResponseError as error:
        return {"stakeholder_metadata": failed_metadata(metadata, "evaluation", error,
                                                     "finalized_stakeholders")}

    for evaluation in result.provided_stakeholders:
        missing = [
            field for field in ("name", "involvement", "summary", "justification")
            if not drafts[evaluation.stakeholder_id][field]
        ]
        if missing:
            evaluation.detail_verdict = "not_met"
            if not evaluation.detail_feedback:
                evaluation.detail_feedback = "Please provide: " + ", ".join(missing) + "."
        if evaluation.detail_verdict != "met":
            evaluation.relevance_verdict = "not_evaluated"
            evaluation.relevance_feedback = ""
            evaluation.overlap_verdict = "not_evaluated"
            evaluation.overlap_feedback = ""
            evaluation.overlap_stakeholder_ids = []
        for category in ("detail", "relevance", "overlap"):
            if getattr(evaluation, category + "_verdict") == "met":
                setattr(evaluation, category + "_feedback", "")
        for category in ("detail", "relevance", "overlap"):
            if getattr(evaluation, category + "_verdict") == "met":
                setattr(evaluation, category + "_feedback", "")
        verdicts = (
            evaluation.detail_verdict,
            evaluation.relevance_verdict,
            evaluation.overlap_verdict,
        )
        evaluation.overall_verdict = (
            "not_met" if "not_met" in verdicts
            else "met" if all(v == "met" for v in verdicts)
            else "not_evaluated"
        )

    return {
        "stakeholder_metadata": {
            **metadata,
            "evaluation": result.model_dump(),
            "model_error": None,
            "evaluated_draft_version": metadata["draft_version"],
        }
    }


def stakeholders_ready(state: AgentState) -> bool:
    """Readiness is checked by the graph, separately from user confirmation."""
    metadata = state["stakeholder_metadata"]
    evaluation = metadata["evaluation"]
    if (
        not metadata["drafts"] or not evaluation or metadata.get("model_error")
        or metadata["response_feedback"]
        or metadata["evaluated_draft_version"] != metadata["draft_version"]
    ):
        return False
    results = evaluation["provided_stakeholders"]
    return (
        len(results) == len(metadata["drafts"])
        and {e["stakeholder_id"] for e in results}
        == {d["stakeholder_id"] for d in metadata["drafts"]}
        and all(e["overall_verdict"] == "met" for e in results)
    )


def prompt_stakeholder_refinement(state: AgentState) -> AgentState:
    """Display current drafts and actionable evaluation feedback."""
    metadata = state["stakeholder_metadata"]
    if (metadata.get("model_error")
            or metadata["evaluated_draft_version"] != metadata["draft_version"]):
        error = metadata.get("model_error")
        if error and error["stage"] == "response":
            explanation = "I couldn't apply that reply. Your drafts are unchanged. Please rephrase the requested changes using their IDs."
        else:
            explanation = "The latest evaluation could not be completed. Current drafts are shown below; these are not current passing results. Enter RETRY to evaluate them again, or describe changes."
        records = "\n\n".join(_record(d) for d in metadata["drafts"]) or "No drafts yet."
        message = explanation + "\n\n" + records
        return {"stakeholder_metadata": _collect_response(metadata, message)}
    evaluations = {
        e["stakeholder_id"]: e
        for e in metadata["evaluation"]["provided_stakeholders"]
    }
    ready, needs_work = [], []
    for draft in metadata["drafts"]:
        evaluation = evaluations[draft["stakeholder_id"]]
        if evaluation["overall_verdict"] == "met":
            ready.append(_record(draft))
            continue
        feedback = []
        if evaluation["detail_verdict"] != "met":
            feedback.append(prompt.STAKEHOLDER_DETAIL_FEEDBACK_TEMPLATE.format(**evaluation))
        else:
            if evaluation["relevance_verdict"] != "met":
                feedback.append(prompt.STAKEHOLDER_RELEVANCE_FEEDBACK_TEMPLATE.format(**evaluation))
            if evaluation["overlap_verdict"] != "met":
                feedback.append(prompt.STAKEHOLDER_OVERLAP_FEEDBACK_TEMPLATE.format(
                    related_stakeholder_ids=", ".join(
                        evaluation["overlap_stakeholder_ids"]
                    ) or "not yet established",
                    overlap_feedback=evaluation["overlap_feedback"],
                ))
        needs_work.append(prompt.STAKEHOLDER_FEEDBACK_TEMPLATE.format(
            stakeholder_id=draft["stakeholder_id"], name=draft["name"],
            feedback="\n".join(feedback),
        ))

    sections = []
    if metadata["response_feedback"]:
        sections.append(metadata["response_feedback"])
    if ready:
        sections.append(prompt.STAKEHOLDER_READY_SECTION_TEMPLATE.format(
            stakeholders="\n\n".join(ready)
        ))
    if needs_work:
        sections.append(prompt.STAKEHOLDER_FEEDBACK_SECTION_TEMPLATE.format(
            stakeholders="\n\n".join(needs_work)
        ))
    if not metadata["drafts"]:
        sections.append("Please provide at least one stakeholder.")
    message = prompt.STAKEHOLDER_FOLLOW_UP_PROMPT.format(sections="\n\n".join(sections))
    return {"stakeholder_metadata": _collect_response(metadata, message)}


def confirm_stakeholders(state: AgentState) -> AgentState:
    """Ask the engineer to confirm the exact current version of the list."""
    if not stakeholders_ready(state):
        raise ValueError("Stakeholders are not ready for final confirmation.")
    metadata = state["stakeholder_metadata"]
    message = prompt.STAKEHOLDER_CONFIRMATION_PROMPT.format(
        draft_version=metadata["draft_version"],
        stakeholders="\n\n".join(_record(d) for d in metadata["drafts"]),
    )
    updated = _collect_response(metadata, message)
    if updated["latest_user_response"].strip().upper() == "APPROVE":
        updated["user_confirmed"] = True
        updated["approved_version"] = metadata["draft_version"]
    return {"stakeholder_metadata": updated}


def finalize_stakeholders(state: AgentState) -> AgentState:
    """Expose confirmed stakeholders for the next stage; storage is deferred."""
    metadata = state["stakeholder_metadata"]
    if (
        not stakeholders_ready(state) or not metadata["user_confirmed"]
        or metadata["approved_version"] != metadata["draft_version"]
    ):
        raise ValueError("The current stakeholder list requires explicit approval.")
    records = [StakeHolderDraft.model_validate(d).model_dump() for d in metadata["drafts"]]
    return {"stakeholder_metadata": {**metadata, "finalized_stakeholders": records}}
