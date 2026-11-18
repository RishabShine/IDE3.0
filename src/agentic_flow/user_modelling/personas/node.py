import json

from langchain_core.messages import HumanMessage, SystemMessage

from agentic_flow.core.models import base_model
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


def _turn_input(metadata) -> dict[str, str]:
    return {
        "user_feedback": metadata["latest_user_response"],
        "last_prompt_to_user": metadata["last_prompt_to_user"],
        "evaluation": _json(metadata["evaluation"]),
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
    context = {}  #! REPLACE WITH ACTUAL INTENT DATA WHEN MERGED
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
            "latest_user_response": "",
            "response_feedback": "",
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
    request = prompt.PERSONA_RESPONSE_PROMPT.format(**_turn_input(metadata))
    # Each call gets reusable context, current records, and the latest exchange.
    # Older turns are not retained or replayed.
    messages = [
        SystemMessage(content=prompt.PERSONA_RESPONSE_INSTRUCTIONS),
        HumanMessage(content=metadata["initial_context_message"]),
        HumanMessage(content=request),
    ]
    result = PersonaResponse.model_validate(
        persona_response_processor.invoke(messages)
    )

    drafts = {d["persona_id"]: dict(d) for d in metadata["drafts"]}
    next_number = metadata["next_draft_number"]

    removed = result.removed_persona_ids
    updated = [u.persona_id for u in result.updates if u.persona_id is not None]
    if len(removed) != len(set(removed)) or len(updated) != len(set(updated)):
        raise ValueError("The response contains repeated persona operations.")
    if not set(removed + updated).issubset(drafts) or set(removed) & set(updated):
        raise ValueError("The response references an unknown or removed draft ID.")

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
            "user_confirmed": False,
            "approved_version": None,
            "finalized_personas": [],
        }
    }


def evaluate_personas(state: AgentState) -> AgentState:
    """Evaluate current drafts with reusable context and only the latest exchange."""
    metadata = state["persona_metadata"]
    request = prompt.PERSONA_EVALUATION_PROMPT.format(**_turn_input(metadata))
    messages = [
        SystemMessage(content=prompt.PERSONA_EVALUATION_INSTRUCTIONS),
        HumanMessage(content=metadata["initial_context_message"]),
        HumanMessage(content=request),
    ]
    result = PersonaEvaluation.model_validate(persona_evaluator.invoke(messages))

    drafts = {d["persona_id"]: d for d in metadata["drafts"]}
    ids = [e.persona_id for e in result.provided_personas]
    if len(ids) != len(set(ids)) or set(ids) != set(drafts):
        raise ValueError("The evaluation must cover each current draft exactly once.")

    stakeholders = _stakeholders(state)
    section_fields = [*prompt.PERSONA_FIELD_LABELS, "varied"]
    for evaluation in result.provided_personas:
        draft = drafts[evaluation.persona_id]
        inferred = evaluation.inferred_stakeholder_id
        if inferred is not None and inferred not in stakeholders:
            raise ValueError("The evaluation proposes an unknown stakeholder ID.")
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

        for field in section_fields:
            if evaluation.relevance_verdict != "met":
                setattr(evaluation, field + "_verdict", "not_evaluated")
                setattr(evaluation, field + "_feedback", "")
            elif field not in ("demographics", "varied") and not draft[field].strip():
                setattr(evaluation, field + "_verdict", "not_met")
                if not getattr(evaluation, field + "_feedback"):
                    setattr(evaluation, field + "_feedback", "Please provide this detail.")
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
            "evaluated_draft_version": version,
        }
    }


def personas_ready(state: AgentState) -> bool:
    """Readiness is checked by the graph, separately from user confirmation."""
    metadata = state["persona_metadata"]
    evaluation = metadata["evaluation"]
    if (
        not metadata["drafts"] or not evaluation
        or metadata["response_feedback"]
        or metadata["evaluated_draft_version"] != metadata["draft_version"]
    ):
        return False
    results = evaluation["provided_personas"]
    return (
        len(results) == len(metadata["drafts"])
        and {e["persona_id"] for e in results}
        == {d["persona_id"] for d in metadata["drafts"]}
        and all(e["overall_verdict"] == "met" for e in results)
        and all(d["stakeholder_id"] in _stakeholders(state)
                and d["varied_justification"].strip() for d in metadata["drafts"])
    )


def prompt_persona_refinement(state: AgentState) -> AgentState:
    """Display current drafts and actionable evaluation feedback."""
    metadata = state["persona_metadata"]
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
        draft_version=metadata["draft_version"],
        personas="\n\n".join(_record(d) for d in metadata["drafts"]),
    )
    updated = _collect_response(metadata, message)
    if updated["latest_user_response"].strip().upper() == "APPROVE":
        updated["user_confirmed"] = True
        updated["approved_version"] = metadata["draft_version"]
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
