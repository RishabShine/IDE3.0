import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agentic_flow.core.models import base_model
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


def _name(value: str) -> str:
    return " ".join(value.split()).casefold()


def _turn_input(metadata) -> dict[str, str]:
    return {
        "user_feedback": metadata["latest_user_response"],
        "stakeholders": _json(metadata["drafts"]),
        "pending_suggestions": _json(metadata["pending_suggestions"]),
        "declined_suggestions": _json(metadata["declined_suggestions"]),
    }


def _collect_response(metadata, message: str) -> dict:
    # do not mutate state before interrupt(): this node restarts when resumed
    response = get_user_input(prompt=message)
    if not isinstance(response, str):
        raise ValueError("The stakeholder response must be text.")
    return {
        **metadata,
        "messages": [
            *metadata["messages"],
            AIMessage(content=message),
            HumanMessage(content=response),
        ],
        "latest_user_response": response,
        "user_confirmed": False,
        "approved_version": None,
    }


def _record(draft) -> str:
    return prompt.STAKEHOLDER_RECORD_TEMPLATE.format(
        **{**draft, "involvement": draft["involvement"] or "Not established"}
    )


def initialize_stakeholders(state: AgentState) -> AgentState:
    """Start the conversation once, without calling the model or reading files."""
    if state.get("stakeholder_metadata", {}).get("initialized"):
        return {}

    #! full upstream context can be supplied here when its structure is ready
    # preserve all currently available intent metadata
    context = state.get("captured_intent")
    if context is None:
        context = {
            "project_context": state.get("project_context", ""),
            "intent_metadata": state.get("intent_metadata", {}),
        }

    return {
        "stakeholder_metadata": {
            "initialized": True,
            "intent_context": context,
            "messages": [
                SystemMessage(content=prompt.STAKEHOLDER_CONVERSATION_INSTRUCTIONS),
                HumanMessage(
                    content=prompt.STAKEHOLDER_INTENT_CONTEXT_PROMPT.format(
                        intent_context=_json(context)
                    )
                ),
            ],
            "drafts": [],
            "next_draft_id": 1,
            "draft_version": 0,
            "pending_suggestions": [],
            "declined_suggestions": [],
            "evaluation": None,
            "latest_user_response": "",
            "response_feedback": "",
            "user_confirmed": False,
            "approved_version": None,
            "finalized_stakeholders": [],
        }
    }


def prompt_initial_stakeholders(state: AgentState) -> AgentState:
    """Display the starter guidance and wait for the first stakeholder list."""
    metadata = _collect_response(
        state["stakeholder_metadata"], prompt.STAKEHOLDER_STARTER_PROMPT
    )
    return {"stakeholder_metadata": metadata}


def process_stakeholder_response(state: AgentState) -> AgentState:
    """Interpret the reply, then apply explicit edits and suggestion decisions."""
    metadata = state["stakeholder_metadata"]
    request = prompt.STAKEHOLDER_RESPONSE_PROMPT.format(**_turn_input(metadata))
    # Use the same conversation, with task-specific instructions for this call.
    # The evaluator's system message requests a different response schema.
    messages = [
        SystemMessage(content=prompt.STAKEHOLDER_RESPONSE_INSTRUCTIONS),
        *[m for m in metadata["messages"] if not isinstance(m, SystemMessage)],
        HumanMessage(content=request),
    ]
    result = StakeHolderResponse.model_validate(
        stakeholder_response_processor.invoke(messages)
    )

    drafts = {d["stakeholder_id"]: dict(d) for d in metadata["drafts"]}
    pending = {_name(s["name"]): dict(s) for s in metadata["pending_suggestions"]}
    declined = {_name(s["name"]): dict(s) for s in metadata["declined_suggestions"]}
    next_id = metadata["next_draft_id"]

    removed = result.removed_stakeholder_ids
    updated = [u.stakeholder_id for u in result.updates if u.stakeholder_id is not None]
    if len(removed) != len(set(removed)) or len(updated) != len(set(updated)):
        raise ValueError("The response contains repeated stakeholder operations.")
    if not set(removed + updated).issubset(drafts) or set(removed) & set(updated):
        raise ValueError("The response references an unknown or removed draft ID.")

    for stakeholder_id in removed:
        removed_draft = drafts.pop(stakeholder_id)
        declined[_name(removed_draft["name"])] = {
            "name": removed_draft["name"],
            "summary": removed_draft["summary"],
            "justification": removed_draft["justification"],
            "reason": "The user removed this group from the stakeholder drafts.",
        }

    decisions_seen = set()
    for decision in result.suggestion_decisions:
        key = _name(decision.name)
        if key not in pending or key in decisions_seen:
            raise ValueError("The response references an unknown or repeated suggestion.")
        decisions_seen.add(key)
        suggestion = pending.pop(key)
        if decision.decision == "decline":
            declined[key] = {**suggestion, "reason": decision.reason}
        else:
            drafts[next_id] = StakeHolderDraft(
                stakeholder_id=next_id,
                involvement=None,
                **suggestion,
            ).model_dump()
            next_id += 1

    for update in result.updates:
        stakeholder_id = update.stakeholder_id
        if stakeholder_id is None:
            stakeholder_id = next_id
            next_id += 1
        if not update.name.strip():
            raise ValueError("A stakeholder draft must have a name.")
        record = update.model_dump()
        record["stakeholder_id"] = stakeholder_id
        drafts[stakeholder_id] = StakeHolderDraft.model_validate(record).model_dump()

    current = list(drafts.values())
    current_names = {_name(d["name"]) for d in current}
    # The user may explicitly introduce a previously declined group themselves.
    pending = {k: v for k, v in pending.items() if k not in current_names}
    declined = {k: v for k, v in declined.items() if k not in current_names}
    return {
        "stakeholder_metadata": {
            **metadata,
            "drafts": current,
            "next_draft_id": next_id,
            "draft_version": metadata["draft_version"] + (current != metadata["drafts"]),
            "pending_suggestions": list(pending.values()),
            "declined_suggestions": list(declined.values()),
            "evaluation": None,
            "response_feedback": result.clarification_feedback,
            "user_confirmed": False,
            "approved_version": None,
            "finalized_stakeholders": [],
            "messages": [
                *metadata["messages"],
                HumanMessage(content=request),
                AIMessage(content=result.model_dump_json()),
            ],
        }
    }


def evaluate_stakeholders(state: AgentState) -> AgentState:
    """Evaluate the current drafts using the retained conversation."""
    metadata = state["stakeholder_metadata"]
    request = prompt.STAKEHOLDER_EVALUATION_PROMPT.format(**_turn_input(metadata))
    messages = [*metadata["messages"], HumanMessage(content=request)]
    result = StakeHolderEvaluation.model_validate(stakeholder_evaluator.invoke(messages))

    drafts = {d["stakeholder_id"]: d for d in metadata["drafts"]}
    ids = [e.stakeholder_id for e in result.provided_stakeholders]
    if len(ids) != len(set(ids)) or set(ids) != set(drafts):
        raise ValueError("The evaluation must cover each current draft exactly once.")

    for evaluation in result.provided_stakeholders:
        related = evaluation.overlap_stakeholder_ids
        if not set(related).issubset(drafts) or evaluation.stakeholder_id in related:
            raise ValueError("The evaluation contains an invalid overlap reference.")
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

    pending = {_name(s["name"]): s for s in metadata["pending_suggestions"]}
    excluded = {_name(s["name"]) for s in metadata["declined_suggestions"]}
    excluded.update(_name(d["name"]) for d in metadata["drafts"])
    for suggestion in result.suggested_stakeholders:
        key = _name(suggestion.name)
        if key and key not in excluded and key not in pending:
            pending[key] = suggestion.model_dump()

    return {
        "stakeholder_metadata": {
            **metadata,
            "evaluation": result.model_dump(),
            "pending_suggestions": list(pending.values()),
            "messages": [*messages, AIMessage(content=result.model_dump_json())],
        }
    }


def stakeholders_ready(state: AgentState) -> bool:
    """Readiness is checked by the graph, separately from user confirmation."""
    metadata = state["stakeholder_metadata"]
    evaluation = metadata["evaluation"]
    if (
        not metadata["drafts"] or not evaluation
        or metadata["pending_suggestions"] or metadata["response_feedback"]
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
    """Display current drafts, actionable feedback, and outstanding suggestions."""
    metadata = state["stakeholder_metadata"]
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
                        map(str, evaluation["overlap_stakeholder_ids"])
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
    if metadata["pending_suggestions"]:
        sections.append(prompt.SUGGESTED_STAKEHOLDERS_SECTION_TEMPLATE.format(
            suggestions="\n\n".join(
                prompt.SUGGESTED_STAKEHOLDER_TEMPLATE.format(**s)
                for s in metadata["pending_suggestions"]
            )
        ))
    if not metadata["drafts"]:
        sections.append("Please provide at least one stakeholder, or accept a suggestion.")
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
