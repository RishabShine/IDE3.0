import re

from langchain_core.messages import HumanMessage, SystemMessage

from agentic_flow.capture_intent.context_expected_benefits_current_situation import prompts
from agentic_flow.capture_intent.context_expected_benefits_current_situation.schema import (
    CurrentSituationEvaluation,
    ExpectedBenefitsEvaluation,
)
from agentic_flow.capture_intent.sson.prompts import SINGLE_STATEMENT_OF_NEED_REVISE_PROMPT
from agentic_flow.core.models import base_model
from agentic_flow.core.shared_nodes import get_user_choice, get_user_input, tell_user
from agentic_flow.state import AgentState

problem_evaluator = base_model.with_structured_output(CurrentSituationEvaluation)
benefit_evaluator = base_model.with_structured_output(ExpectedBenefitsEvaluation)

MAX_TRIES = 2  # evaluations per stage before the user may confirm the list as it is


def _listing(items: list[dict], sources: bool = False) -> str:
    """One line per item. `sources` adds the user's words each item came from."""
    lines = []
    for item in items:
        line = f"- **{item['id']}:** {item['description']}"
        if "addresses" in item:  # a benefit
            fixes = ", ".join(item["addresses"]) or "none"
            line += f" (fixes: {fixes}; measure: {item['measure'] or 'none yet'}; {item['kind']})"
        if sources:
            line += f'\n  - You said: "{item["source"]}"'
        lines.append(line)
    return "\n".join(lines) or "(none)"


def _norm(text: str | None) -> str:
    return " ".join((text or "").casefold().split()).strip(" .\"'")


def _passes(criteria, ignore=()) -> bool:
    return all(v != "not_met" for name, v in criteria.model_dump().items() if name not in ignore)


def _sson(state: AgentState) -> str:
    return state["intent_metadata"]["single_statement_intent"]


def _user_context(state: AgentState) -> str:
    """Everything the user has told us so far: the SSON and the saved items."""
    metadata = state.get("context_metadata", {})
    items = [*metadata.get("problems", []), *metadata.get("benefits", [])]
    return " ".join([_sson(state), *(f"{i['description']} {i.get('measure') or ''}" for i in items)])


def benefits_basis(state: AgentState) -> dict:
    """What the benefits are graded against. If it changes, they are graded again."""
    return {"sson": _sson(state), "problems": state["context_metadata"]["problems"]}


def _evaluate(evaluator, system_prompt: str, user_input: str, attempt: int, asked_about: list[str]):
    message = f"<user_input>{user_input}</user_input>"
    if asked_about:  # so an answer to our question rewrites that item, not adds a new one
        message += f"\n<asked_about>{', '.join(asked_about)}</asked_about>"
    if attempt >= MAX_TRIES:  # the model tends to skip the example unless reminded here
        message += "\n" + prompts.EXAMPLE_REMINDER.format(attempt=attempt)
    return evaluator.invoke([SystemMessage(content=system_prompt), HumanMessage(content=message)])


def _merge(existing: list[dict], extracted: list, prefix: str, next_id: int, user_input: str):
    """
    Turn the LLM's list into saved items. IDs stay stable and are never reused, and
    every new or rewritten item must quote the user's message (the 3RA3 rule that
    each item traces to something the user said). An untraced new item is dropped;
    an untraced rewrite keeps the earlier wording.
    Returns [(item, extracted item)], the next free ID number, and the untraced count.
    """
    earlier = {item["id"]: item for item in existing}
    said = _norm(user_input)
    pairs, untraced = [], 0
    for new in extracted:
        old = earlier.pop(new.id, None)  # unknown or repeated IDs count as new
        traced = bool(_norm(new.source)) and _norm(new.source) in said
        if old and new.description == old["description"]:
            item = old
        elif traced:
            item = {
                "id": old["id"] if old else f"{prefix}-{next_id}",
                "description": new.description,
                "source": new.source,
            }
            next_id += not old
        else:
            untraced += 1
            if not old:
                continue
            item = old
        pairs.append((item, new))
    return pairs, next_id, untraced


def _own_numbers(example: str, context: str) -> str:
    """Replace any number in the evaluator's example that the user never gave."""
    known = set(re.findall(r"\d+(?:[.,]\d+)*", context))
    return re.sub(
        r"\d+(?:[.,]\d+)*", lambda m: m.group() if m.group() in known else "[number]", example
    )


def _evaluated(metadata: dict, evaluation, feedback: str, passed: bool, untraced: int, has_items: bool, context: str = "") -> dict:
    """
    The fields every evaluation writes. After MAX_TRIES failed tries the evaluator's
    example is shown and the user may go on to the read-back with the list as it is.
    """
    attempts = metadata.get("attempts", 0) + 1
    if untraced:
        feedback += "\n\n" + prompts.UNTRACED.format(count=untraced)
    if not passed and attempts >= MAX_TRIES:
        # The evaluator sometimes leaves the example out; then ask for it on its own.
        example = evaluation.suggested_example or base_model.invoke(
            prompts.EXAMPLE_FALLBACK.format(context=context, feedback=feedback)
        ).content
        feedback += "\n\n" + prompts.SUGGESTED_EXAMPLE.format(
            example=_own_numbers(example.strip(), context)
        )
    ready = passed
    if not passed and attempts >= MAX_TRIES and has_items:
        ready = True
        feedback += "\n\n" + prompts.TRIES_USED.format(tries=attempts)
    return {
        **metadata,
        "user_input": "",
        "feedback": feedback,
        "passed": passed,
        "ready": ready,
        "attempts": attempts,
    }


def _confirm(state: AgentState, items_key: str, choices: list[str]) -> dict:
    """Read the list back and wait for one of `choices`. After 'no', ask what to change."""
    metadata = state["context_metadata"]
    items = _listing(metadata[items_key], sources=True)
    choice = get_user_choice(
        prompts.CONFIRM.format(
            feedback=metadata.get("feedback", ""),
            items=items,
            choices="\n".join(f"- **{c}** {prompts.CHOICES[c]}" for c in choices),
        ).strip(),
        choices,
    )
    feedback = prompts.CHANGE.format(items=items) if choice == "no" else ""
    return {**metadata, "choice": choice, "feedback": feedback, "attempts": 0, "asked_about": []}


def _confirmed(state: AgentState, metadata: dict) -> dict:
    """The update after a read-back. 'sson' also makes the SSON graph ask again."""
    update = {"context_metadata": metadata}
    if metadata["choice"] == "sson":
        update["intent_metadata"] = {
            **state["intent_metadata"],
            "passed": False,
            "attempt_number": 0,
            "feedback": SINGLE_STATEMENT_OF_NEED_REVISE_PROMPT.format(statement=_sson(state)),
        }
    return update


# --- Current situation (G.2) ------------------------------------------------

def capture_current_situation(state: AgentState) -> AgentState:
    """Show the G.2 starter (or the last feedback) and wait for the user's problems."""
    metadata = state.get("context_metadata", {})
    reply = get_user_input(metadata.get("feedback") or prompts.CAPTURE_CURRENT_SITUATION)
    return {"context_metadata": {**metadata, "user_input": reply}}


def evaluate_current_situation(state: AgentState) -> AgentState:
    """
    Extract the full problem list and grade each problem. Passes if none is not_met.
    With no new user input (the SSON was revised), the existing list is graded again.
    """
    metadata = state["context_metadata"]
    next_id = metadata.get("next_problem_id", 1)
    user_input = metadata.get("user_input") or prompts.RECHECK
    evaluation = _evaluate(
        problem_evaluator,
        prompts.CAPTURE_CURRENT_SITUATION_EVALUATE.format(
            sson=_sson(state),
            previous_items=_listing(metadata.get("problems", [])),
            next_id=f"Problem-{next_id}",
            attempt_number=metadata.get("attempts", 0) + 1,
            current_process=metadata.get("current_process") or "(none)",
        ),
        user_input,
        metadata.get("attempts", 0) + 1,
        metadata.get("asked_about", []),
    )
    context = f"{_user_context(state)} {user_input}"
    if not evaluation.is_attempt:  # keep the list we already have
        return {"context_metadata": _evaluated(metadata, evaluation, evaluation.feedback_to_user, False, 0, False, context)}

    pairs, next_id, untraced = _merge(
        metadata.get("problems", []), evaluation.problems, "Problem", next_id, user_input
    )
    passed = bool(pairs) and all(_passes(new.criteria) for _, new in pairs)
    return {
        "context_metadata": {
            **_evaluated(metadata, evaluation, evaluation.feedback_to_user, passed, untraced, bool(pairs), context),
            "problems": [item for item, _ in pairs],
            "asked_about": [item["id"] for item, new in pairs if not _passes(new.criteria)],
            "next_problem_id": next_id,
            "problems_basis": _sson(state),
            "current_process": evaluation.current_process or metadata.get("current_process"),
        }
    }


def confirm_current_situation(state: AgentState) -> AgentState:
    metadata = _confirm(state, "problems", ["yes", "no", "sson"])
    if metadata["choice"] == "yes":
        tell_user(
            prompts.CONFIRMED_CURRENT_SITUATION.format(
                current_process=metadata.get("current_process") or "(not described)",
                items=_listing(metadata["problems"], sources=True),
            )
        )
    return _confirmed(state, metadata)


# --- Expected benefits (G.3) ------------------------------------------------

def capture_expected_benefits(state: AgentState) -> AgentState:
    """Show the G.3 starter with the confirmed problems (or the last feedback)."""
    metadata = state["context_metadata"]
    reply = get_user_input(
        metadata.get("feedback")
        or prompts.CAPTURE_EXPECTED_BENEFITS.format(problems=_listing(metadata["problems"]))
    )
    return {"context_metadata": {**metadata, "user_input": reply}}


def evaluate_expected_benefits(state: AgentState) -> AgentState:
    """
    Extract the full benefit list and grade each benefit. Passes if no benefit is
    not_met (a missing measure only makes it soft) and every problem is either
    fixed by a benefit or marked out of scope. With no new user input (the SSON or
    the problems were revised), the existing list is graded again.
    """
    metadata = state["context_metadata"]
    problem_ids = [p["id"] for p in metadata["problems"]]
    next_id = metadata.get("next_benefit_id", 1)
    user_input = metadata.get("user_input") or prompts.RECHECK
    evaluation = _evaluate(
        benefit_evaluator,
        prompts.CAPTURE_EXPECTED_BENEFITS_EVALUATE.format(
            sson=_sson(state),
            problems=_listing(metadata["problems"]),
            previous_items=_listing(metadata.get("benefits", [])),
            next_id=f"Benefit-{next_id}",
            attempt_number=metadata.get("attempts", 0) + 1,
        ),
        user_input,
        metadata.get("attempts", 0) + 1,
        metadata.get("asked_about", []),
    )
    context = f"{_user_context(state)} {user_input}"
    if not evaluation.is_attempt:  # keep the list we already have
        return {"context_metadata": _evaluated(metadata, evaluation, evaluation.feedback_to_user, False, 0, False, context)}

    pairs, next_id, untraced = _merge(
        metadata.get("benefits", []), evaluation.benefits, "Benefit", next_id, user_input
    )
    said = _norm(user_input)
    benefits = [
        {
            **item,
            "addresses": [i for i in problem_ids if i in new.addresses],
            # a measure must be the user's own words, from this turn or an earlier one
            "measure": new.measure
            if _norm(new.measure) and (_norm(new.measure) in said or new.measure == item.get("measure"))
            else item.get("measure"),
            "kind": "soft" if new.criteria.measurable == "not_met" else "hard",
        }
        for item, new in pairs
    ]
    out_of_scope = [
        i for i in problem_ids
        if i in evaluation.out_of_scope_problems or i in metadata.get("out_of_scope_problems", [])
    ]
    covered = {i for b in benefits for i in b["addresses"]} | set(out_of_scope)
    uncovered = [i for i in problem_ids if i not in covered]

    feedback = evaluation.feedback_to_user
    if uncovered:
        feedback += (
            f"\n\nNo benefit fixes {', '.join(uncovered)} yet. Add a benefit for each, "
            "or tell me it is out of scope."
        )
    passed = (
        bool(benefits)
        and not uncovered
        and all(_passes(new.criteria, ignore={"measurable"}) for _, new in pairs)
    )
    return {
        "context_metadata": {
            **_evaluated(metadata, evaluation, feedback, passed, untraced, bool(benefits), context),
            "benefits": benefits,
            "asked_about": [
                item["id"] for item, new in pairs if not _passes(new.criteria, ignore={"measurable"})
            ],
            "next_benefit_id": next_id,
            "benefits_basis": benefits_basis(state),
            "out_of_scope_problems": out_of_scope,
        }
    }


def confirm_expected_benefits(state: AgentState) -> AgentState:
    """On 'yes', also publish the whole capture phase as captured_intent for later phases."""
    metadata = _confirm(state, "benefits", ["yes", "no", "problems", "sson"])
    update = _confirmed(state, metadata)
    if metadata["choice"] != "yes":
        return update

    tell_user(
        prompts.CONFIRMED_EXPECTED_BENEFITS.format(
            items=_listing(metadata["benefits"], sources=True),
            out_of_scope=", ".join(metadata.get("out_of_scope_problems", [])) or "none",
        )
    )
    sson = state["intent_metadata"]
    update["captured_intent"] = {
        "project_context": state.get("project_context", ""),
        **{k: sson.get(k) for k in ("single_statement_intent", "what", "how", "why", "success_measure")},
        **{k: metadata.get(k) for k in ("current_process", "problems", "benefits", "out_of_scope_problems")},
    }
    return update
