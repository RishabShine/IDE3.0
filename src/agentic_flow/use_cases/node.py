"""Use case model (3RA3 L13): actors, use cases and «include»/«extend» links.

The model names things; code assigns IDs (Actor-n, UC-n), resolves every name,
keeps only links to known stakeholders and goals, and records rough-model checks
taken from the L13 pitfalls in `issues`. Nothing is dropped silently.
"""
import json

from langchain_core.messages import HumanMessage, SystemMessage

from agentic_flow.capture_intent.common import unflag
from agentic_flow.core.models import base_model
from agentic_flow.goals.node import intent_context
from agentic_flow.state import AgentState
from agentic_flow.use_cases import prompt
from agentic_flow.use_cases.schema import UseCaseModelResponse

use_case_extractor = base_model.with_structured_output(UseCaseModelResponse, method="json_schema")


def _key(name: str | None) -> str:
    return " ".join((name or "").split()).casefold()


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


def _goal_context(state: AgentState) -> list[dict]:
    goals = (state.get("goal_metadata") or {}).get("goals") or []
    return [{"id": g["goal_id"], "statement": unflag(g.get("statement")),
             "goal_type": g.get("goal_type"), "actors": g.get("actors") or [],
             "plans": g.get("plans") or ""} for g in goals]


def prepare_use_case_request(state: AgentState) -> AgentState:
    """Collect the PRD, intent, user model and goals for one modelling call."""
    prd = state.get("prd", "")
    if not isinstance(prd, str) or not prd.strip():
        raise ValueError("A non-empty PRD is required for the use case model.")
    instructions = prompt.USE_CASE_PROMPT.format(
        prd=prd,
        intent_context=json.dumps(intent_context(state.get("captured_intent")), ensure_ascii=False),
        stakeholders=json.dumps((state.get("stakeholder_metadata") or {}).get("stakeholders", []),
                                ensure_ascii=False),
        personas=json.dumps((state.get("persona_metadata") or {}).get("personas", []),
                            ensure_ascii=False),
        goals=json.dumps(_goal_context(state), ensure_ascii=False),
    )
    return {"use_case_metadata": {"instructions": instructions, "system_name": "",
                                  "actors": [], "use_cases": [], "relationships": [],
                                  "issues": []}}


def build_model(response: UseCaseModelResponse, stakeholder_ids: set[str],
                goal_ids: set[str]) -> dict:
    """Turn the model's named output into an ID-linked use case model plus issues."""
    issues: list[str] = []
    actors: list[dict] = []
    actor_by_name: dict[str, str] = {}

    def actor_id(name: str, kind: str = "human", stakeholder_id: str | None = None) -> str | None:
        name = _clean(name)
        if not name:
            return None
        if _key(name) not in actor_by_name:
            aid = f"Actor-{len(actors) + 1}"
            if stakeholder_id is not None and stakeholder_id not in stakeholder_ids:
                issues.append(f"{aid} ({name}) named unknown stakeholder {stakeholder_id}; "
                              "the link was removed.")
                stakeholder_id = None
            actors.append({"actor_id": aid, "name": name, "kind": kind,
                           "stakeholder_id": stakeholder_id})
            actor_by_name[_key(name)] = aid
        return actor_by_name[_key(name)]

    for actor in response.actors:
        actor_id(actor.name, actor.kind, actor.stakeholder_id)

    use_cases: list[dict] = []
    case_by_name: dict[str, str] = {}
    for item in response.use_cases:
        name = _clean(item.name)
        if not name:
            continue
        if _key(name) in case_by_name:
            issues.append(f"Use case '{name}' was listed twice; the copy was dropped.")
            continue
        ucid = f"UC-{len(use_cases) + 1}"
        primary = None
        if _clean(item.primary_actor):
            if _key(item.primary_actor) not in actor_by_name:
                issues.append(f"{ucid} named actor '{_clean(item.primary_actor)}', which was "
                              "not in the actor list; it was added.")
            primary = actor_id(item.primary_actor)
        supporting = []
        for name_ in item.supporting_actors:
            if _clean(name_) and _key(name_) not in actor_by_name:
                issues.append(f"{ucid} named actor '{_clean(name_)}', which was not in the "
                              "actor list; it was added.")
            sid = actor_id(name_)
            if sid and sid != primary and sid not in supporting:
                supporting.append(sid)
        unknown_goals = [g for g in item.goal_ids if g not in goal_ids]
        if unknown_goals:
            issues.append(f"{ucid} named unknown goal(s) {', '.join(unknown_goals)}; "
                          "the links were removed.")
        use_cases.append({
            "use_case_id": ucid, "name": name, "description": _clean(item.description),
            "primary_actor_id": primary, "supporting_actor_ids": supporting,
            "goal_ids": [g for g in dict.fromkeys(item.goal_ids) if g in goal_ids],
        })
        case_by_name[_key(name)] = ucid

    relationships: list[dict] = []
    seen = set()
    for rel in response.relationships:
        source, target = case_by_name.get(_key(rel.source)), case_by_name.get(_key(rel.target))
        if not source or not target:
            issues.append(f"«{rel.kind}» from '{_clean(rel.source)}' to '{_clean(rel.target)}' "
                          "names a use case that does not exist; it was dropped.")
            continue
        if source == target or (rel.kind, source, target) in seen:
            continue
        seen.add((rel.kind, source, target))
        relationships.append({"kind": rel.kind, "source": source, "target": target,
                              "condition": _clean(rel.condition) if rel.kind == "extend" else ""})

    issues.extend(check_model(actors, use_cases, relationships, goal_ids))
    return {"system_name": _clean(response.system_name) or "System", "actors": actors,
            "use_cases": use_cases, "relationships": relationships, "issues": issues}


def check_model(actors, use_cases, relationships, goal_ids) -> list[str]:
    """Rough-model checks from the L13 pitfalls that code can decide."""
    issues = []
    used = {u["primary_actor_id"] for u in use_cases} | {
        a for u in use_cases for a in u["supporting_actor_ids"]}
    for actor in actors:
        if actor["actor_id"] not in used:
            issues.append(f"{actor['actor_id']} ({actor['name']}) takes part in no use case.")
    for case in use_cases:
        if not case["primary_actor_id"]:
            issues.append(f"{case['use_case_id']} has no primary actor.")
        if not case["goal_ids"]:
            issues.append(f"{case['use_case_id']} ({case['name']}) achieves no extracted goal.")
    # Pitfall 1: use cases chained with «include» to show a process order
    includes = {(r["source"], r["target"]) for r in relationships if r["kind"] == "include"}
    for a, b in includes:
        for b2, c in includes:
            if b == b2:
                issues.append(f"{a} → {b} → {c} chains «include» links; use cases are not "
                              "process steps (L13 pitfall 1).")
    for r in relationships:
        if r["kind"] == "extend" and not r["condition"]:
            issues.append(f"{r['source']} «extend» {r['target']} states no condition.")
    covered = {g for u in use_cases for g in u["goal_ids"]}
    for goal in sorted(goal_ids - covered):
        issues.append(f"{goal} is achieved by no use case.")
    return issues


def extract_use_cases(state: AgentState) -> AgentState:
    metadata = state["use_case_metadata"]
    response = UseCaseModelResponse.model_validate(use_case_extractor.invoke([
        SystemMessage(content=prompt.USE_CASE_INSTRUCTIONS),
        HumanMessage(content=metadata["instructions"]),
    ]))
    stakeholder_ids = {s["stakeholder_id"] for s in
                       (state.get("stakeholder_metadata") or {}).get("stakeholders", [])}
    goal_ids = {g["goal_id"] for g in (state.get("goal_metadata") or {}).get("goals", [])}
    return {"use_case_metadata": {**metadata, **build_model(response, stakeholder_ids, goal_ids)}}
