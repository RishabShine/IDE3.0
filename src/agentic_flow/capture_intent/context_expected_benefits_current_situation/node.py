from langchain_core.messages import HumanMessage, SystemMessage

from agentic_flow.capture_intent.common import (
    checked_source,
    flag,
    intent,
    require_prd,
    same_point,
    sourced_items,
    states_exclusion,
    supports,
    to_json,
    traced,
    unflag,
)
from agentic_flow.capture_intent.context_expected_benefits_current_situation import prompts
from agentic_flow.capture_intent.context_expected_benefits_current_situation.schema import (
    CurrentSituationExtraction,
    EnvironmentExtraction,
    ExpectedBenefitsExtraction,
)
from agentic_flow.core.models import base_model
from agentic_flow.state import AgentState

situation_extractor = base_model.with_structured_output(
    CurrentSituationExtraction, method="json_schema"
)
benefit_extractor = base_model.with_structured_output(
    ExpectedBenefitsExtraction, method="json_schema"
)
environment_extractor = base_model.with_structured_output(
    EnvironmentExtraction, method="json_schema"
)

ENVIRONMENT_PREFIX = {
    "effects": "Effect",
    "invariants": "Invariant",
    "constraints": "Constraint",
    "scope_exclusions": "Exclusion",
}


def _ask(extractor, schema, instructions: str, request: str):
    return schema.model_validate(extractor.invoke([
        SystemMessage(content=instructions),
        HumanMessage(content=request),
    ]))


def _public(items: list[dict]) -> list[dict]:
    return [{"id": i["id"], "description": i["description"]} for i in items]


def extract_current_situation(state: AgentState) -> AgentState:
    """G.2: today's process and its problems (Problem-n)."""
    prd = require_prd(state)
    captured = intent(state)
    result = _ask(
        situation_extractor, CurrentSituationExtraction,
        prompts.CURRENT_SITUATION_INSTRUCTIONS,
        prompts.CURRENT_SITUATION_PROMPT.format(
            prd=prd, sson=captured.get("single_statement_intent") or "(none)",
        ),
    )
    return {"captured_intent": {
        **captured,
        "current_situation": " ".join(result.current_situation.split()),
        "problems": sourced_items(result.problems, "Problem", prd),
    }}


def extract_expected_benefits(state: AgentState) -> AgentState:
    """G.3: benefits (Benefit-n) linked to the problems they fix.

    Links to unknown problems are dropped. A measure must appear in the
    benefit's own quoted PRD sentence; otherwise it is cleared and the benefit
    is kept as a soft benefit. A problem is out of scope only when a PRD quote
    says it will not be addressed and that quote is about that problem.
    """
    prd = require_prd(state)
    captured = intent(state)
    problems = captured.get("problems") or []
    problem_ids = {p["id"] for p in problems}
    result = _ask(
        benefit_extractor, ExpectedBenefitsExtraction,
        prompts.EXPECTED_BENEFITS_INSTRUCTIONS,
        prompts.EXPECTED_BENEFITS_PROMPT.format(
            prd=prd,
            sson=captured.get("single_statement_intent") or "(none)",
            problems=to_json(_public(problems)) if problems else "(none)",
        ),
    )

    benefits = []
    for item in result.benefits:
        description = " ".join(item.description.split())
        if not description:
            continue
        source = checked_source(item.source, description, prd)
        measure = " ".join((item.measure or "").split()) or None
        if measure and not (source and traced(measure, source)):
            measure = None
        benefits.append({
            "id": f"Benefit-{len(benefits) + 1}",
            "description": description if source else flag(description),
            "source": source,
            "addresses": [p for p in dict.fromkeys(item.addresses) if p in problem_ids],
            "measure": measure,
            "kind": "hard" if measure else "soft",
        })

    by_id = {p["id"]: p for p in problems}
    out_of_scope = [
        item.problem_id for item in result.out_of_scope_problems
        if item.problem_id in by_id
        and traced(item.source, prd)
        and states_exclusion(item.source)
        and supports(item.source, unflag(by_id[item.problem_id]["description"]))
    ]
    return {"captured_intent": {
        **captured,
        "benefits": benefits,
        "out_of_scope_problems": list(dict.fromkeys(out_of_scope)),
    }}


def _split_benefits_and_effects(benefits: list[dict], effects: list[dict]):
    """Keep each point in one place when the model lists it as a benefit and an effect.

    A soft benefit that fixes no problem is really an effect: it is dropped from the
    benefits. A benefit with a measure or a problem link stays a benefit, and the
    duplicate effect is dropped. Both lists are renumbered; nothing links to these
    IDs yet.
    """
    def is_duplicate(a, b):
        return same_point(unflag(a["description"]), unflag(b["description"]))

    kept_benefits = [
        b for b in benefits
        if b["kind"] == "hard" or b["addresses"]
        or not any(is_duplicate(b, e) for e in effects)
    ]
    kept_effects = [e for e in effects if not any(is_duplicate(e, b) for b in kept_benefits)]

    def renumber(items, prefix):
        return [{**item, "id": f"{prefix}-{n}"} for n, item in enumerate(items, start=1)]

    return renumber(kept_benefits, "Benefit"), renumber(kept_effects, "Effect")


def extract_environment(state: AgentState) -> AgentState:
    """E.5 effects, E.6 invariants, constraints and scope exclusions.

    A point listed both as a benefit and as an effect is kept in one place only.
    """
    prd = require_prd(state)
    captured = intent(state)
    benefits = captured.get("benefits") or []
    result = _ask(
        environment_extractor, EnvironmentExtraction,
        prompts.ENVIRONMENT_INSTRUCTIONS,
        prompts.ENVIRONMENT_PROMPT.format(
            prd=prd, benefits=to_json(_public(benefits)) if benefits else "(none)",
        ),
    )
    environment = {
        field: sourced_items(getattr(result, field), prefix, prd)
        for field, prefix in ENVIRONMENT_PREFIX.items()
    }
    benefits, environment["effects"] = _split_benefits_and_effects(
        benefits, environment["effects"]
    )
    return {"captured_intent": {**captured, "benefits": benefits, **environment}}
