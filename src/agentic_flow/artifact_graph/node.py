"""Assemble every artifact extracted from the PRD into one connected graph.

No model call: this step only reads what earlier steps saved in the state,
turns each artifact into a node, turns each recorded relationship into an
edge, and records gaps (missing artifacts, broken links, unconnected items).
To add a new artifact type, write a collector and add it to COLLECTORS.

"""
from typing import Any, Callable

from agentic_flow.artifact_graph.schema import (
    ArtifactEdge,
    ArtifactGap,
    ArtifactGraph,
    ArtifactNode,
)
from agentic_flow.goal2story.artifacts import collect_stories
from agentic_flow.state import AgentState


INTENT_ID = "Intent-1"

Collected = tuple[list[ArtifactNode], list[ArtifactEdge]]


def _node(artifact_id: str, artifact_type: str, label: str,
          data: dict[str, Any]) -> ArtifactNode:
    return {"id": artifact_id, "type": artifact_type, "label": label, "data": data}


def _without(record: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k not in keys}


def _has_intent(state: AgentState) -> bool:
    intent = state.get("captured_intent") or {}
    return bool((intent.get("single_statement_intent") or "").strip())


def collect_intent(state: AgentState) -> Collected:
    """Intent, plus the problems and benefits captured with it."""
    if not _has_intent(state):
        return [], []
    intent = state["captured_intent"]

    nodes = [_node(INTENT_ID, "intent", intent["single_statement_intent"].strip(),
                   _without(intent, "problems", "benefits"))]
    edges: list[ArtifactEdge] = []
    for problem in intent.get("problems") or []:
        nodes.append(_node(problem["id"], "problem", problem.get("description", ""),
                           _without(problem, "id")))
        edges.append({"source": problem["id"], "target": INTENT_ID,
                      "relation": "motivates"})
    for benefit in intent.get("benefits") or []:
        nodes.append(_node(benefit["id"], "benefit", benefit.get("description", ""),
                           _without(benefit, "id")))
        edges.append({"source": benefit["id"], "target": INTENT_ID,
                      "relation": "realizes"})
        for problem_id in benefit.get("addresses") or []:
            edges.append({"source": benefit["id"], "target": problem_id,
                          "relation": "addresses"})
    return nodes, edges


def collect_stakeholders(state: AgentState) -> Collected:
    records = (state.get("stakeholder_metadata") or {}).get("stakeholders") or []
    link_to_intent = _has_intent(state)
    nodes, edges = [], []
    for record in records:
        sid = record["stakeholder_id"]
        nodes.append(_node(sid, "stakeholder", record.get("name", ""),
                           _without(record, "stakeholder_id")))
        if link_to_intent:
            edges.append({"source": sid, "target": INTENT_ID,
                          "relation": "concerned_with"})
    return nodes, edges


def collect_personas(state: AgentState) -> Collected:
    records = (state.get("persona_metadata") or {}).get("personas") or []
    nodes, edges = [], []
    for record in records:
        pid = record["persona_id"]
        label = record.get("name") or record.get("role") or pid
        nodes.append(_node(pid, "persona", label, _without(record, "persona_id")))
        if record.get("stakeholder_id"):
            edges.append({"source": pid, "target": record["stakeholder_id"],
                          "relation": "represents"})
    return nodes, edges


def collect_goals(state: AgentState) -> Collected:
    """Goals refine the intent, deliver benefits and involve stakeholders."""
    records = (state.get("goal_metadata") or {}).get("goals") or []
    link_to_intent = _has_intent(state)
    nodes, edges = [], []
    for record in records:
        gid = record["goal_id"]
        nodes.append(_node(gid, "goal", record.get("statement", ""),
                           _without(record, "goal_id")))
        if link_to_intent:
            edges.append({"source": gid, "target": INTENT_ID, "relation": "refines"})
        for benefit_id in record.get("benefit_ids") or []:
            edges.append({"source": gid, "target": benefit_id, "relation": "delivers"})
        for actor in record.get("actors") or []:
            if actor.get("stakeholder_id"):
                edges.append({"source": gid, "target": actor["stakeholder_id"],
                              "relation": "involves"})
    return nodes, edges


def collect_use_cases(state: AgentState) -> Collected:
    """Use cases achieve goals and serve the stakeholder behind their primary actor."""
    meta = state.get("use_case_metadata") or {}
    actors = {a["actor_id"]: a for a in meta.get("actors") or []}
    nodes, edges = [], []
    for case in meta.get("use_cases") or []:
        ucid = case["use_case_id"]
        primary = actors.get(case.get("primary_actor_id")) or {}
        nodes.append(_node(ucid, "use_case", case.get("name", ""),
                           {**_without(case, "use_case_id"),
                            "primary_actor": primary.get("name")}))
        for goal_id in case.get("goal_ids") or []:
            edges.append({"source": ucid, "target": goal_id, "relation": "achieves"})
        if primary.get("stakeholder_id"):
            edges.append({"source": ucid, "target": primary["stakeholder_id"],
                          "relation": "serves"})
    return nodes, edges


# (artifact type named in "missing" gaps, collector), upstream to downstream
COLLECTORS: list[tuple[str, Callable[[AgentState], Collected]]] = [
    ("intent", collect_intent),
    ("stakeholder", collect_stakeholders),
    ("persona", collect_personas),
    ("goal", collect_goals),
    ("use_case", collect_use_cases),
    ("story", collect_stories),
]
# Stories exist only after goal2story runs, so having none is not a gap.
OPTIONAL_TYPES = {"story"}


def build_artifact_graph(state: AgentState) -> ArtifactGraph:
    nodes: list[ArtifactNode] = []
    edges: list[ArtifactEdge] = []
    gaps: list[ArtifactGap] = []
    seen: set[str] = set()

    for artifact_type, collect in COLLECTORS:
        found_nodes, found_edges = collect(state)
        if artifact_type not in OPTIONAL_TYPES and not any(
                n["type"] == artifact_type for n in found_nodes):
            gaps.append({"kind": "missing_artifacts", "artifact_id": None,
                         "detail": f"No {artifact_type} artifacts were extracted."})
        for found in found_nodes:
            if found["id"] in seen:
                gaps.append({"kind": "duplicate_id", "artifact_id": found["id"],
                             "detail": f"{found['id']} appears more than once; "
                                       "kept the first."})
                continue
            seen.add(found["id"])
            nodes.append(found)
        edges.extend(found_edges)

    # keep only links whose both ends exist; report the rest
    valid_edges: list[ArtifactEdge] = []
    for edge in edges:
        missing = [end for end in (edge["source"], edge["target"]) if end not in seen]
        if missing:
            gaps.append({"kind": "dangling_link", "artifact_id": edge["source"],
                         "detail": f"{edge['source']} {edge['relation']} "
                                   f"{edge['target']}, but {', '.join(missing)} "
                                   "does not exist."})
        elif edge not in valid_edges:
            valid_edges.append(edge)

    gaps.extend(_find_unconnected(nodes, valid_edges))
    return {"nodes": nodes, "edges": valid_edges, "gaps": gaps}


def _find_unconnected(nodes: list[ArtifactNode],
                      edges: list[ArtifactEdge]) -> list[ArtifactGap]:
    outgoing = {(e["source"], e["relation"]) for e in edges}
    incoming = {(e["target"], e["relation"]) for e in edges}
    has_goals = any(n["type"] == "goal" for n in nodes)
    has_stories = any(n["type"] == "story" for n in nodes)
    has_use_cases = any(n["type"] == "use_case" for n in nodes)
    gaps: list[ArtifactGap] = []
    for n in nodes:  # every check runs: one artifact can have several gaps
        if n["type"] == "persona" and (n["id"], "represents") not in outgoing:
            gaps.append({"kind": "unlinked_persona", "artifact_id": n["id"],
                         "detail": f"{n['id']} ({n['label']}) is not linked to a "
                                   "stakeholder."})
        if (n["type"] == "stakeholder" and n["data"].get("involvement") == "direct"
              and (n["id"], "represents") not in incoming):
            gaps.append({"kind": "stakeholder_without_persona", "artifact_id": n["id"],
                         "detail": f"{n['id']} ({n['label']}) is a direct stakeholder "
                                   "with no persona."})
        if n["type"] == "problem" and (n["id"], "addresses") not in incoming:
            gaps.append({"kind": "unaddressed_problem", "artifact_id": n["id"],
                         "detail": f"{n['id']} is not addressed by any benefit."})
        if (n["type"] == "goal" and (n["id"], "delivers") not in outgoing
              and (n["id"], "involves") not in outgoing):
            gaps.append({"kind": "unlinked_goal", "artifact_id": n["id"],
                         "detail": f"{n['id']} delivers no benefit and involves no "
                                   "stakeholder."})
        if (has_use_cases and n["type"] == "goal"
              and (n["id"], "achieves") not in incoming):
            gaps.append({"kind": "goal_without_use_case", "artifact_id": n["id"],
                         "detail": f"{n['id']} is achieved by no use case."})
        if n["type"] == "use_case" and (n["id"], "achieves") not in outgoing:
            gaps.append({"kind": "use_case_without_goal", "artifact_id": n["id"],
                         "detail": f"{n['id']} ({n['label']}) achieves no goal."})
        if (has_stories and n["type"] == "goal"
              and (n["id"], "implements") not in incoming):
            gaps.append({"kind": "goal_without_story", "artifact_id": n["id"],
                         "detail": f"{n['id']} has no user story."})
        if (has_goals and n["type"] == "benefit"
              and (n["id"], "delivers") not in incoming):
            gaps.append({"kind": "benefit_without_goal", "artifact_id": n["id"],
                         "detail": f"{n['id']} is not delivered by any goal."})
    return gaps


def assemble_artifact_graph(state: AgentState) -> AgentState:
    """Graph node: store the assembled artifact graph in the state."""
    return {"artifact_graph": build_artifact_graph(state)}
