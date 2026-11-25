"""Goal2Story's nodes and links for the artifact graph.

Returns (nodes, edges) in the artifact graph's format. Register it in
artifact_graph/node.py COLLECTORS as ("goal", collect_goal2story).

Edges point from the lower-level artifact to the higher-level one:
    goal        --achieves-->     intent
    actor       --helps_reach-->  goal
    actor       --drawn_from-->   stakeholder
    impact      --impact_of-->    actor
    deliverable --supports-->     impact
    story       --implements-->   deliverable
"""
from typing import Any

GOAL_ID = "Goal-1"
INTENT_ID = "Intent-1"  # the artifact graph's intent node

TYPE = {"actors": "actor", "impacts": "impact", "deliverables": "deliverable", "stories": "story"}
RELATION = {"impacts": "impact_of", "deliverables": "supports", "stories": "implements"}


def _name(value: str) -> str:
    return " ".join(str(value).split()).casefold()


def _label(level: str, item: dict[str, Any]) -> str:
    if level == "actors":
        return item["name"]
    if level == "stories":
        return item["text"]
    return item["description"]


def _stakeholder_ids(state) -> dict[str, str]:
    """Actors name their stakeholder; match it by name or by ID."""
    lookup = {}
    for record in (state.get("stakeholder_metadata") or {}).get("stakeholders") or []:
        sid = record["stakeholder_id"]
        lookup[_name(record.get("name", ""))] = sid
        lookup[_name(sid)] = sid
    return lookup


def _has_intent(state) -> bool:
    intent = state.get("captured_intent") or {}
    return bool((intent.get("single_statement_intent") or "").strip())


def collect_goal2story(state) -> tuple[list[dict], list[dict]]:
    meta = state.get("goal2story_metadata") or {}
    if not meta.get("goal"):
        return [], []

    nodes = [{"id": GOAL_ID, "type": "goal", "label": meta["goal"], "data": {}}]
    edges = []
    if _has_intent(state):
        edges.append({"source": GOAL_ID, "target": INTENT_ID, "relation": "achieves"})

    stakeholders = _stakeholder_ids(state)
    for level, artifact_type in TYPE.items():
        for item in meta.get(level) or []:
            data = {k: v for k, v in item.items() if k not in ("id", "parent_id")}
            nodes.append({"id": item["id"], "type": artifact_type,
                          "label": _label(level, item), "data": data})
            if level == "actors":
                edges.append({"source": item["id"], "target": GOAL_ID,
                              "relation": "helps_reach"})
                sid = stakeholders.get(_name(item.get("stakeholder", "")))
                if sid:
                    edges.append({"source": item["id"], "target": sid,
                                  "relation": "drawn_from"})
            elif item.get("parent_id"):
                edges.append({"source": item["id"], "target": item["parent_id"],
                              "relation": RELATION[level]})
    return nodes, edges
