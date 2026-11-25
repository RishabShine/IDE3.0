"""Goal2Story's user stories as artifact-graph nodes and links.

Registered in artifact_graph/node.py COLLECTORS. Edges point from the
lower-level artifact to the higher-level one:
    story --implements-->   goal         (the extracted goal it was written for)
    story --performed_by--> stakeholder  (through the goal actor it names)
"""
from typing import Any


def collect_stories(state) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    meta = state.get("goal2story_metadata") or {}
    nodes, edges = [], []
    for story in meta.get("stories") or []:
        data = {k: v for k, v in story.items() if k not in ("id", "parent_id", "text")}
        nodes.append({"id": story["id"], "type": "story", "label": story["text"], "data": data})
        edges.append({"source": story["id"], "target": story["parent_id"],
                      "relation": "implements"})
        if story.get("stakeholder_id"):
            edges.append({"source": story["id"], "target": story["stakeholder_id"],
                          "relation": "performed_by"})
    return nodes, edges
