"""Impact analysis: what an engineer's edits mean for the artifacts traced to them.

collect_candidates (code)  follow trace links from each changed artifact, plus any
                           artifact that refers to a deleted ID; removing links
                           to deleted IDs is proposed here, without the model
assess_impact (model)      one call: unaffected / revise / obsolete per candidate
validate_proposals (code)  keep only known IDs and revisable fields; everything
                           else becomes a note. Nothing is applied here: the
                           engineer accepts or rejects each proposal.

Input: state["impact_request"]["changes"], each {key, action, before, after}.
Output: state["impact_report"].
"""
import json
from collections import deque

from langchain_core.messages import HumanMessage, SystemMessage

from agentic_flow.artifact_graph.node import INTENT_ID, build_artifact_graph
from agentic_flow.core.models import base_model
from agentic_flow.impact_analysis import prompt
from agentic_flow.impact_analysis.schema import ImpactResponse
from agentic_flow.state import AgentState

impact_model = base_model.with_structured_output(ImpactResponse, method="json_schema")

SITUATION_ID = "Current-situation"
MAX_CANDIDATES = 40

# collection -> (state key, list key, id key, revisable text fields, type, stage)
COLLECTIONS = {
    "problems": ("captured_intent", "problems", "id", ("description",), "problem", "context"),
    "benefits": ("captured_intent", "benefits", "id", ("description", "measure"), "benefit", "context"),
    "effects": ("captured_intent", "effects", "id", ("description",), "effect", "context"),
    "invariants": ("captured_intent", "invariants", "id", ("description",), "invariant", "context"),
    "constraints": ("captured_intent", "constraints", "id", ("description",), "constraint", "context"),
    "scope_exclusions": ("captured_intent", "scope_exclusions", "id", ("description",),
                         "scope_exclusion", "context"),
    "stakeholders": ("stakeholder_metadata", "stakeholders", "stakeholder_id",
                     ("name", "summary", "justification"), "stakeholder", "stakeholders"),
    "personas": ("persona_metadata", "personas", "persona_id",
                 ("name", "role", "status_and_trust_level", "demographics", "ksa", "gmc",
                  "usage_patterns"), "persona", "personas"),
    "goals": ("goal_metadata", "goals", "goal_id", ("statement", "plans", "justification"),
              "goal", "goals"),
}
SSON_FIELDS = ("single_statement_intent", "what", "how", "why", "success_measure",
               "context_and_objective")
NEW_TYPE_COLLECTION = {"problem": "problems", "benefit": "benefits", "effect": "effects",
                       "invariant": "invariants", "constraint": "constraints",
                       "scope_exclusion": "scope_exclusions", "goal": "goals"}


def artifact_id_of(key: str) -> str:
    """Store key (problems:Problem-2, singleton:sson) -> artifact ID (Problem-2, Intent-1)."""
    if key == "singleton:sson":
        return INTENT_ID
    if key == "singleton:situation":
        return SITUATION_ID
    return key.split(":", 1)[1]


def index_artifacts(state: AgentState) -> dict[str, dict]:
    """Every artifact the engineer can see, by ID, with its store key and revisable fields."""
    out: dict[str, dict] = {}
    for collection, (parent, key, id_key, fields, kind, stage) in COLLECTIONS.items():
        for record in (state.get(parent) or {}).get(key) or []:
            aid = record[id_key]
            out[aid] = {"id": aid, "key": f"{collection}:{aid}", "collection": collection,
                        "type": kind, "stage": stage, "record": record,
                        "fields": {f: record.get(f) for f in fields},
                        "label": record.get("description") or record.get("statement")
                        or record.get("name") or record.get("role") or aid}
    intent = state.get("captured_intent") or {}
    if intent.get("single_statement_intent"):
        out[INTENT_ID] = {"id": INTENT_ID, "key": "singleton:sson", "collection": "singleton:sson",
                          "type": "intent", "stage": "sson", "record": intent,
                          "fields": {f: intent.get(f) for f in SSON_FIELDS},
                          "label": intent["single_statement_intent"]}
    if intent.get("current_situation"):
        out[SITUATION_ID] = {"id": SITUATION_ID, "key": "singleton:situation",
                             "collection": "singleton:situation", "type": "situation",
                             "stage": "context", "record": {"current_situation": intent["current_situation"]},
                             "fields": {"current_situation": intent["current_situation"]},
                             "label": intent["current_situation"]}
    for case in (state.get("use_case_metadata") or {}).get("use_cases") or []:
        uid = case["use_case_id"]
        out[uid] = {"id": uid, "key": f"usecases:{uid}", "collection": "use_cases",
                    "type": "use_case", "stage": "use_cases", "record": case, "fields": {},
                    "label": case.get("name", uid)}
    return out


def _unlink(entry: dict, deleted: str) -> dict | None:
    """The field values with every link to `deleted` removed, or None if none."""
    record, fields = entry["record"], {}
    for field in ("addresses", "benefit_ids", "goal_ids"):
        if deleted in (record.get(field) or []):
            fields[field] = [x for x in record[field] if x != deleted]
    if record.get("stakeholder_id") == deleted:
        fields["stakeholder_id"] = None
    if any(a.get("stakeholder_id") == deleted for a in record.get("actors") or []):
        fields["actors"] = [{**a, "stakeholder_id": None} if a.get("stakeholder_id") == deleted
                            else a for a in record["actors"]]
    return fields or None


def collect_candidates(state: AgentState) -> AgentState:
    changes = (state.get("impact_request") or {}).get("changes") or []
    artifacts = index_artifacts(state)
    graph = build_artifact_graph(state)
    neighbours: dict[str, list[tuple[str, str]]] = {}
    for e in graph["edges"]:
        sentence = f"{e['source']} {e['relation'].replace('_', ' ')} {e['target']}"
        neighbours.setdefault(e["source"], []).append((e["target"], sentence))
        neighbours.setdefault(e["target"], []).append((e["source"], sentence))

    changed = [artifact_id_of(c["key"]) for c in changes]
    via: dict[str, list[str]] = {}

    def add(aid: str, why: str) -> None:
        if aid in artifacts and aid not in changed:
            reasons = via.setdefault(aid, [])
            if why not in reasons:
                reasons.append(why)

    auto = []
    for change, start in zip(changes, changed):
        if start == SITUATION_ID:
            for aid, entry in artifacts.items():
                if entry["type"] == "problem":
                    add(aid, "the current situation describes where this problem comes from")
            continue
        # breadth-first along trace links; the intent links to nearly everything, so
        # walk past it only when it is what changed
        depth_limit = 1 if start == INTENT_ID else 2
        queue, seen = deque([(start, 0)]), {start}
        while queue:
            node, depth = queue.popleft()
            if depth == depth_limit or (node == INTENT_ID and node != start):
                continue
            for other, sentence in neighbours.get(node, []):
                if other not in seen:
                    seen.add(other)
                    add(other, sentence)
                    queue.append((other, depth + 1))
        if change.get("action") == "deleted":
            for aid, entry in artifacts.items():
                if aid == start:
                    continue
                fields = _unlink(entry, start)
                if fields:
                    add(aid, f"refers to the deleted {start}")
                    auto.append({"kind": "unlink", "artifact_id": aid, "key": entry["key"],
                                 "collection": entry["collection"], "type": entry["type"],
                                 "stage": entry["stage"], "label": entry["label"],
                                 "fields": fields,
                                 "before": {f: entry["record"].get(f) for f in fields},
                                 "reason": f"{start} was deleted; remove the link to it."})

    candidates = [{"id": aid, "type": artifacts[aid]["type"], "text": artifacts[aid]["label"],
                   "linked_because": reasons,
                   "revisable_fields": artifacts[aid]["fields"]}
                  for aid, reasons in list(via.items())[:MAX_CANDIDATES]]
    notes = []
    if len(via) > MAX_CANDIDATES:
        notes.append(f"{len(via) - MAX_CANDIDATES} more linked artifacts were not assessed "
                     f"(limit {MAX_CANDIDATES}).")
    return {"impact_report": {"changes": changes, "candidates": candidates, "proposals": auto,
                              "assessments": [], "new_artifacts": [], "unaffected": [],
                              "notes": notes}}


def assess_impact(state: AgentState) -> AgentState:
    report = state["impact_report"]
    if not report["candidates"]:
        return {}
    changes = [{k: c.get(k) for k in ("key", "action", "before", "after")}
               for c in report["changes"]]
    response = ImpactResponse.model_validate(impact_model.invoke([
        SystemMessage(content=prompt.IMPACT_INSTRUCTIONS),
        HumanMessage(content=prompt.IMPACT_REQUEST.format(
            prd=state.get("prd", ""),
            changes=json.dumps(changes, ensure_ascii=False, indent=1),
            candidates=json.dumps(report["candidates"], ensure_ascii=False, indent=1),
        )),
    ]))
    return {"impact_report": {**report,
                              "assessments": [a.model_dump() for a in response.assessments],
                              "new_artifacts": [n.model_dump() for n in response.new_artifacts]}}


def validate_proposals(state: AgentState) -> AgentState:
    report = state["impact_report"]
    artifacts = index_artifacts(state)
    candidate_ids = {c["id"] for c in report["candidates"]}
    proposals, unaffected, notes = list(report["proposals"]), [], list(report["notes"])
    assessed, rerun_reasons = set(), []

    def proposal(kind: str, entry: dict, reason: str, fields=None) -> dict:
        return {"kind": kind, "artifact_id": entry["id"], "key": entry["key"],
                "collection": entry["collection"], "type": entry["type"],
                "stage": entry["stage"], "label": entry["label"], "fields": fields or {},
                "before": {f: entry["record"].get(f) for f in (fields or {})},
                "reason": reason}

    for a in report["assessments"]:
        aid, reason = a["artifact_id"], " ".join(a["reason"].split())
        if aid not in candidate_ids or aid in assessed:
            notes.append(f"The model assessed {aid}, which was not a candidate; ignored.")
            continue
        assessed.add(aid)
        entry = artifacts[aid]
        if a["verdict"] == "unaffected":
            unaffected.append({"artifact_id": aid, "type": entry["type"], "reason": reason})
        elif entry["type"] == "use_case":
            rerun_reasons.append(f"{aid}: {reason}")
        elif a["verdict"] == "obsolete" and not entry["collection"].startswith("singleton:"):
            proposals.append(proposal("remove", entry, reason))
        else:
            fields = {}
            for change in a.get("changes") or []:
                value = " ".join(change["value"].split())
                if change["field"] not in entry["fields"]:
                    notes.append(f"{aid}: '{change['field']}' cannot be revised here; ignored.")
                elif value and value != (entry["fields"][change["field"]] or ""):
                    fields[change["field"]] = value
            if fields:
                proposals.append(proposal("revise", entry, reason, fields))
            else:
                notes.append(f"{aid} was marked {a['verdict']} without a usable edit: {reason}")
    for candidate in report["candidates"]:
        if candidate["id"] not in assessed:
            unaffected.append({"artifact_id": candidate["id"], "type": candidate["type"],
                               "reason": "Not assessed by the model."})
    if rerun_reasons:
        proposals.append({"kind": "rerun", "artifact_id": None, "key": None,
                          "collection": "use_cases", "type": "use_case", "stage": "use_cases",
                          "label": "Use case model", "fields": {}, "before": {},
                          "reason": "Rebuild the use case model: " + " ".join(rerun_reasons)})
    for new in report["new_artifacts"]:
        collection = NEW_TYPE_COLLECTION[new["type"]]
        text = " ".join(new["text"].split())
        if not text:
            continue
        field = "statement" if collection == "goals" else "description"
        proposals.append({"kind": "add", "artifact_id": None, "key": None,
                          "collection": collection, "type": new["type"],
                          "stage": COLLECTIONS[collection][5], "label": text,
                          "fields": {field: text}, "before": {},
                          "reason": " ".join(new["reason"].split())})
    for number, p in enumerate(proposals, start=1):
        p["proposal_id"] = f"P-{number}"
        p["status"] = "pending"
    stages = sorted({artifacts[c["id"]]["stage"] for c in report["candidates"]})
    return {"impact_report": {**report, "proposals": proposals, "unaffected": unaffected,
                              "notes": notes, "stages": stages}}
