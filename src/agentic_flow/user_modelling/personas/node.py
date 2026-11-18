import json

from langchain_core.messages import HumanMessage, SystemMessage

from agentic_flow.core.models import base_model
from agentic_flow.core.refinement import (
    MAX_REFINEMENT_ATTEMPTS, asked_about, checks_pass, review_note,
)
from agentic_flow.core.validation import (
    ModelResponseError, check_coverage, check_operations, failed_metadata, invoke_checked,
)
from agentic_flow.core.shared_nodes import get_user_input
from agentic_flow.state import AgentState
from agentic_flow.user_modelling.personas import prompt
from agentic_flow.user_modelling.personas.schema import (
    PersonaDraft,
    PersonaEvaluation,
    PersonaResponse,
)


# JSON schema mode uses Ollama's structured output instead of tool calling.
persona_evaluator = base_model.with_structured_output(
    PersonaEvaluation, method="json_schema"
)
persona_response_processor = base_model.with_structured_output(
    PersonaResponse, method="json_schema"
)


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _response_input(metadata) -> dict[str, str]:
    return {
        "user_feedback": metadata["latest_user_response"],
        "last_prompt_to_user": metadata["last_prompt_to_user"],
        "asked_about": _json(asked_about(metadata, "provided_personas", "persona_id")),
        "personas": _json(metadata["drafts"]),
    }


def _collect_response(metadata, message: str) -> dict:
    # do not mutate state before interrupt(): this node restarts when resumed
    response = get_user_input(prompt=message)
    if not isinstance(response, str):
        raise ValueError("The persona response must be text.")
    return {
        **metadata,
        "last_prompt_to_user": message,
        "latest_user_response": response,
        "user_confirmed": False,
        "approved_version": None,
    }


def _record(draft) -> str:
    return prompt.PERSONA_RECORD_TEMPLATE.format(**draft)


def _stakeholders(state: AgentState) -> dict:
    records = state.get("stakeholder_metadata", {}).get("finalized_stakeholders", [])
    return {record["stakeholder_id"]: record for record in records}


def start_personas(state: AgentState) -> AgentState:
    """Prepare reusable context and collect the first reply in a single node.

    Nothing is written before interrupt(). On resume, preparing the same local
    metadata again is safe; the node commits it together with the user's reply.
    """
    context = state.get("captured_intent", {})
    stakeholders = _stakeholders(state)
    if not stakeholders:
        raise ValueError("Personas require finalized stakeholders first.")

    metadata = state.get("persona_metadata")
    if not metadata or not metadata.get("initialized"):
        metadata = {
            "initialized": True,
            "initial_context_message": prompt.PERSONA_INTENT_CONTEXT_PROMPT.format(
                stakeholders=_json(list(stakeholders.values())), intent_context=_json(context)
            ),
            "last_prompt_to_user": "",
            "drafts": [],
            "next_draft_number": 1,
            "draft_version": 0,
            "evaluation": None,
            "evaluated_draft_version": None,
            "refinement_attempts": 0,
            "latest_user_response": "",
            "response_feedback": "",
            "model_error": None,
            "user_confirmed": False,
            "approved_version": None,
            "finalized_personas": [],
        }
    metadata = _collect_response(
        metadata, prompt.PERSONA_STARTER_PROMPT.format(
            stakeholders=_json(list(stakeholders.values()))
        )
    )
    return {"persona_metadata": metadata}


def process_persona_response(state: AgentState) -> AgentState:
    """Interpret the reply, then apply user-requested additions, edits, and removals."""
    metadata = state["persona_metadata"]
    if (metadata.get("model_error")
            and metadata["model_error"]["stage"] == "evaluation"
            and metadata["latest_user_response"].strip().upper() == "RETRY"):
        return {"persona_metadata": {**metadata, "model_error": None, "response_feedback": ""}}
    request = prompt.PERSONA_RESPONSE_PROMPT.format(**_response_input(metadata))
    # Each call gets reusable context, current records, and the latest exchange.
    # Older turns are not retained or replayed.
    messages = [
        SystemMessage(content=prompt.PERSONA_RESPONSE_INSTRUCTIONS),
        HumanMessage(content=metadata["initial_context_message"]),
        HumanMessage(content=request),
    ]
    drafts = {d["persona_id"]: dict(d) for d in metadata["drafts"]}
    next_number = metadata["next_draft_number"]
    try:
        result = invoke_checked(
            persona_response_processor, PersonaResponse, messages,
            lambda result: check_operations(result, drafts, "persona_id", next_number),
        )
    except ModelResponseError as error:
        return {"persona_metadata": failed_metadata(metadata, "response", error,
                                                     "finalized_personas")}

    removed = result.removed_persona_ids
    for persona_id in removed:
        drafts.pop(persona_id)

    for update in result.updates:
        persona_id = update.persona_id
        if persona_id is None:
            persona_id = f"Persona-{next_number}"
            next_number += 1
        record = update.model_dump()
        record["persona_id"] = persona_id
        old = drafts.get(persona_id)
        profile_changed = old is None or any(
            record[field] != old[field]
            for field in record if field != "varied_justification"
        )
        # Response processing cannot grant or retain a stale VARIED rationale.
        record["varied_justification"] = "" if profile_changed else old["varied_justification"]
        drafts[persona_id] = PersonaDraft.model_validate(record).model_dump()

    current = list(drafts.values())
    return {
        "persona_metadata": {
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
            "finalized_personas": [],
        }
    }


def evaluate_personas(state: AgentState) -> AgentState:
    """Evaluate current records against project data, without replaying feedback."""
    metadata = state["persona_metadata"]
    request = prompt.PERSONA_EVALUATION_PROMPT.format(personas=_json(metadata["drafts"]))
    messages = [
        SystemMessage(content=prompt.PERSONA_EVALUATION_INSTRUCTIONS),
        HumanMessage(content=metadata["initial_context_message"]),
        HumanMessage(content=request),
    ]
    drafts = {d["persona_id"]: d for d in metadata["drafts"]}

    def validate(result):
        check_coverage(result.provided_personas, drafts, "persona_id")
        for item in result.provided_personas:
            if (item.inferred_stakeholder_id is not None
                    and item.inferred_stakeholder_id not in _stakeholders(state)):
                raise ValueError("An inferred link must reference a finalized stakeholder ID.")

    try:
        result = invoke_checked(persona_evaluator, PersonaEvaluation, messages, validate)
    except ModelResponseError as error:
        return {"persona_metadata": failed_metadata(metadata, "evaluation", error,
                                                     "finalized_personas")}

    stakeholders = _stakeholders(state)
    section_fields = [*prompt.PERSONA_FIELD_LABELS, "varied"]
    for evaluation in result.provided_personas:
        draft = drafts[evaluation.persona_id]
        link = draft["stakeholder_id"]
        if link is None:
            evaluation.relevance_verdict = "not_evaluated"
            evaluation.relevance_feedback = evaluation.relevance_feedback or (
                "Please identify or confirm the corresponding stakeholder."
            )
        elif link not in stakeholders:
            evaluation.relevance_verdict = "not_met"
            evaluation.relevance_feedback = "Please select a finalized stakeholder ID."
        else:
            evaluation.inferred_stakeholder_id = None

        if evaluation.relevance_verdict == "met":
            evaluation.relevance_feedback = ""
            if not draft["demographics"].strip():
                evaluation.demographics_verdict = "met"
                evaluation.demographics_feedback = ""
        for field in section_fields:
            if evaluation.relevance_verdict != "met":
                setattr(evaluation, field + "_verdict", "not_evaluated")
                setattr(evaluation, field + "_feedback", "")
            elif field not in ("demographics", "varied") and not draft[field].strip():
                setattr(evaluation, field + "_verdict", "not_met")
                if not getattr(evaluation, field + "_feedback"):
                    setattr(evaluation, field + "_feedback", "Please provide this detail.")
        # The template makes demographics optional; absence is not a failed check.
        if evaluation.relevance_verdict == "met" and not draft["demographics"].strip():
            evaluation.demographics_verdict = "met"
            evaluation.demographics_feedback = ""
        for field in ["relevance", *section_fields]:
            if getattr(evaluation, field + "_verdict") == "met":
                setattr(evaluation, field + "_feedback", "")
        for field in section_fields:
            if getattr(evaluation, field + "_verdict") == "met":
                setattr(evaluation, field + "_feedback", "")
        # A passing VARIED result must include the generated explanation.
        if (evaluation.relevance_verdict == "met"
                and evaluation.varied_verdict == "met"
                and not evaluation.varied_justification.strip()):
            evaluation.varied_verdict = "not_met"
            evaluation.varied_feedback = "A grounded VARIED justification is still needed."
        verdicts = [evaluation.relevance_verdict] + [
            getattr(evaluation, field + "_verdict") for field in section_fields
        ]
        evaluation.overall_verdict = (
            "not_met" if "not_met" in verdicts
            else "met" if all(v == "met" for v in verdicts)
            else "not_evaluated"
        )
        if evaluation.overall_verdict != "met":
            evaluation.varied_justification = ""
        drafts[evaluation.persona_id] = {
            **draft, "varied_justification": evaluation.varied_justification
        }

    current = list(drafts.values())
    version = metadata["draft_version"] + (current != metadata["drafts"])
    return {
        "persona_metadata": {
            **metadata,
            "drafts": current,
            "draft_version": version,
            "evaluation": result.model_dump(),
            "model_error": None,
            "evaluated_draft_version": version,
            "refinement_attempts": metadata.get("refinement_attempts", 0) + 1,
        }
    }


def personas_ready(state: AgentState) -> bool:
    """Readiness is checked by the graph, separately from user confirmation."""
    metadata = state["persona_metadata"]
    evaluation = metadata["evaluation"]
    if (
        not metadata["drafts"] or not evaluation or metadata.get("model_error")
        or metadata["response_feedback"]
        or metadata["evaluated_draft_version"] != metadata["draft_version"]
    ):
        return False
    results = evaluation["provided_personas"]
    return (
        len(results) == len(metadata["drafts"])
        and {e["persona_id"] for e in results}
        == {d["persona_id"] for d in metadata["drafts"]}
        and (checks_pass(metadata, "provided_personas")
             or metadata.get("refinement_attempts", 0) >= MAX_REFINEMENT_ATTEMPTS)
        and all(d["stakeholder_id"] in _stakeholders(state) for d in metadata["drafts"])
        and (not checks_pass(metadata, "provided_personas")
             or all(d["varied_justification"].strip() for d in metadata["drafts"]))
    )


def prompt_persona_refinement(state: AgentState) -> AgentState:
    """Display current drafts and actionable evaluation feedback."""
    metadata = state["persona_metadata"]
    if (metadata.get("model_error")
            or metadata["evaluated_draft_version"] != metadata["draft_version"]):
        error = metadata.get("model_error")
        if error and error["stage"] == "response":
            explanation = "I couldn't apply that reply. Your drafts are unchanged. Please rephrase the requested changes using their IDs."
        elif not error:
            explanation = metadata["response_feedback"] or "Please provide the records you want to refine."
        else:
            explanation = "The latest evaluation could not be completed. Current drafts are shown below; these are not current passing results. Enter RETRY to evaluate them again, or describe changes."
        records = "\n\n".join(_record(d) for d in metadata["drafts"]) or "No drafts yet."
        message = explanation + "\n\n" + records
        return {"persona_metadata": _collect_response(metadata, message)}
    evaluations = {
        e["persona_id"]: e
        for e in metadata["evaluation"]["provided_personas"]
    }
    ready, needs_work = [], []
    for draft in metadata["drafts"]:
        evaluation = evaluations[draft["persona_id"]]
        if evaluation["overall_verdict"] == "met":
            ready.append(_record(draft))
            continue
        feedback = []
        if evaluation["relevance_verdict"] != "met":
            text = evaluation["relevance_feedback"]
            if evaluation["inferred_stakeholder_id"]:
                text += " Proposed link: " + evaluation["inferred_stakeholder_id"] + ". Please confirm."
            feedback.append(prompt.PERSONA_FIELD_FEEDBACK_TEMPLATE.format(
                field_label="Relevance", feedback=text,
            ))
        else:
            for field, label in {**prompt.PERSONA_FIELD_LABELS, "varied": "VARIED"}.items():
                if evaluation[field + "_verdict"] != "met":
                    feedback.append(prompt.PERSONA_FIELD_FEEDBACK_TEMPLATE.format(
                        field_label=label, feedback=evaluation[field + "_feedback"],
                    ))
        needs_work.append(prompt.PERSONA_FEEDBACK_TEMPLATE.format(
            persona_id=draft["persona_id"], name=draft["name"],
            feedback="\n".join(feedback),
        ))

    sections = []
    if metadata["response_feedback"]:
        sections.append(metadata["response_feedback"])
    if ready:
        sections.append(prompt.PERSONA_READY_SECTION_TEMPLATE.format(
            personas="\n\n".join(ready)
        ))
    if needs_work:
        sections.append(prompt.PERSONA_FEEDBACK_SECTION_TEMPLATE.format(
            personas="\n\n".join(needs_work)
        ))
    if not metadata["drafts"]:
        sections.append("Please provide at least one persona.")
    message = prompt.PERSONA_FOLLOW_UP_PROMPT.format(sections="\n\n".join(sections))
    return {"persona_metadata": _collect_response(metadata, message)}


def confirm_personas(state: AgentState) -> AgentState:
    """Ask the engineer to confirm the exact current version of the list."""
    if not personas_ready(state):
        raise ValueError("Personas are not ready for final confirmation.")
    metadata = state["persona_metadata"]
    message = prompt.PERSONA_CONFIRMATION_PROMPT.format(
        review_note=review_note(metadata, "provided_personas", "persona_id"),
        draft_version=metadata["draft_version"],
        personas="\n\n".join(_record(d) for d in metadata["drafts"]),
    )
    updated = _collect_response(metadata, message)
    if updated["latest_user_response"].strip().upper() == "APPROVE":
        updated["user_confirmed"] = True
        updated["approved_version"] = metadata["draft_version"]
    else:
        # A new round starts after the engineer chooses to change the read-back.
        updated["refinement_attempts"] = 0
    return {"persona_metadata": updated}


def finalize_personas(state: AgentState) -> AgentState:
    """Expose confirmed personas for the next stage; storage is deferred."""
    metadata = state["persona_metadata"]
    if (
        not personas_ready(state) or not metadata["user_confirmed"]
        or metadata["approved_version"] != metadata["draft_version"]
    ):
        raise ValueError("The current persona list requires explicit approval.")
    records = [PersonaDraft.model_validate(d).model_dump() for d in metadata["drafts"]]
    return {"persona_metadata": {**metadata, "finalized_personas": records}}
