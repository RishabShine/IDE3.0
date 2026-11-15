import json
from functools import cache

from langchain_core.messages import HumanMessage, SystemMessage

from agentic_flow.core.models import base_model
from agentic_flow.core.shared_nodes import get_user_input
from agentic_flow.goal2story import prompt
from agentic_flow.goal2story.schema import (
    ActorList,
    ActorRevision,
    DeliverableList,
    DeliverableRevision,
    GeneratedStory,
    ImpactList,
    ImpactRevision,
    InvestCheck,
    StoryRevision,
)
from agentic_flow.state import AgentState

DEFAULT_N_PER_PARENT = 2  # the paper's default: 2 × 2 × 2 = 8 stories per goal

LEVELS = ("actors", "impacts", "deliverables", "stories")
PARENT = {"actors": None, "impacts": "actors", "deliverables": "impacts", "stories": "deliverables"}
PREFIX = {"actors": "A", "impacts": "I", "deliverables": "D", "stories": "US"}
FIELDS = {
    "actors": ("name", "description", "stakeholder"),
    "impacts": ("description",),
    "deliverables": ("description",),
    "stories": ("actor", "action", "expected_outcome"),
}
REVISION_SCHEMA = {
    "actors": ActorRevision,
    "impacts": ImpactRevision,
    "deliverables": DeliverableRevision,
    "stories": StoryRevision,
}
INVEST_ORDER = ("independent", "negotiable", "valuable", "estimable", "small", "testable")


# helpers
# -----------------------------------------------------------------------------

def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _name(value: str) -> str:
    return " ".join(value.split()).casefold()


def _is_approve(text: str) -> bool:
    return text.strip().upper() == "APPROVE"


@cache
def _model(schema):
    # JSON schema mode uses Ollama's structured output instead of tool calling.
    return base_model.with_structured_output(schema, method="json_schema")


def _call(schema, messages):
    """Call the model for `schema`, with one Format Doctor repair attempt.

    Goal2Story runs a Format Doctor after every agent: if the JSON is invalid,
    ask again for valid JSON only. Parse and validation errors are ValueErrors;
    connection errors are not, so they are raised straight away.
    """
    model = _model(schema)
    try:
        return schema.model_validate(model.invoke(messages))
    except ValueError as error:
        repair = HumanMessage(content=prompt.FORMAT_REPAIR_PROMPT.format(error=str(error)[:500]))
        return schema.model_validate(model.invoke([*messages, repair]))


def _items_by_id(meta) -> dict[str, dict]:
    return {item["id"]: item for level in LEVELS for item in meta[level]}


def _chain(meta, item) -> list[dict]:
    """The item's ancestors, top-down (actor → impact → deliverable)."""
    lookup = _items_by_id(meta)
    chain = []
    parent_id = item.get("parent_id")
    while parent_id is not None:
        parent = lookup[parent_id]
        chain.insert(0, parent)
        parent_id = parent.get("parent_id")
    return chain


def _public(item) -> dict:
    """The fields the model sees for an item (no internal bookkeeping)."""
    return {k: v for k, v in item.items() if k not in ("invest", "text")}


def _ref_info(meta, trace=()) -> dict[str, str]:
    return {
        "anchors": _json(meta["context"]),
        "goal": meta["goal"],
        "trace": _json([_public(i) for i in trace]) if trace else "(none)",
    }


def _new_id(meta, level, parent_id) -> str:
    """Stable IDs that show the parent: A-1, I-1.2, D-1.2.1. Stories: US-1, US-2."""
    if level in ("actors", "stories"):
        key, suffix = PREFIX[level], ""
    else:
        key = parent_id
        suffix = parent_id.split("-", 1)[1] + "."
    number = meta["next_index"].get(key, 1)
    meta["next_index"][key] = number + 1
    return f"{PREFIX[level]}-{suffix}{number}"


def _article(noun: str) -> str:
    if noun.lower().startswith(("a ", "an ", "the ")):
        return noun
    return ("an " if noun[:1].lower() in "aeiou" else "a ") + noun


def _story_text(story) -> str:
    action = story["action"].strip().rstrip(".")
    if action.lower().startswith("to "):
        action = action[3:]
    outcome = story["expected_outcome"].strip().rstrip(".")
    return f"As {_article(story['actor'].strip())}, I want to {action}, so that {outcome}."


def _make_item(meta, level, parent_id, fields: dict) -> dict:
    item = {"id": _new_id(meta, level, parent_id), "parent_id": parent_id}
    item.update({f: fields[f].strip() for f in FIELDS[level]})
    if level == "stories":
        item["text"] = _story_text(item)
        item["invest"] = None
    return item


def _copy_meta(state) -> dict:
    meta = state["goal2story_metadata"]
    copied = {**meta, "next_index": dict(meta["next_index"])}
    for level in LEVELS:
        copied[level] = [dict(i) for i in meta[level]]
    return copied


# initialization and goal confirmation
# -----------------------------------------------------------------------------

def _proposed_goal(captured_intent) -> str:
    goals = (captured_intent or {}).get("goals") or []
    if not goals:
        return ""
    goal = goals[0]
    if isinstance(goal, dict):
        goal = goal.get("text") or goal.get("statement") or goal.get("goal") or ""
    return str(goal).strip()


def initialize_goal2story(state: AgentState) -> AgentState:
    """Collect the context anchors once, without calling the model."""
    existing = state.get("goal2story_metadata") or {}
    if existing.get("initialized"):
        return {}

    #! full upstream context (goals, benefits, scope, personas) can be read here
    # when lanes 1 and 2 provide it; for now, use everything currently available
    captured = state.get("captured_intent")
    stakeholders = (state.get("stakeholder_metadata") or {}).get("finalized_stakeholders", [])
    statement = (state.get("intent_metadata") or {}).get("single_statement_intent", "")
    context = {
        "statement_of_need": statement,
        "project_context": state.get("project_context", ""),
        "captured_intent": captured,
        "confirmed_stakeholders": stakeholders,
    }
    context = {k: v for k, v in context.items() if v}

    return {
        "goal2story_metadata": {
            "initialized": True,
            "n_per_parent": existing.get("n_per_parent", DEFAULT_N_PER_PARENT),
            "context": context,
            "proposed_goal": _proposed_goal(captured),
            "goal": "",
            "goal_confirmed": False,
            "actors": [],
            "impacts": [],
            "deliverables": [],
            "stories": [],
            "next_index": {},
            "latest_user_response": "",
            "response_feedback": "",
            "approved_levels": [],
            "edit_log": [],
            "open_questions": [],
            "finalized_stories": [],
        }
    }


def confirm_goal(state: AgentState) -> AgentState:
    """Ask the engineer to approve the proposed goal or type their own."""
    meta = state["goal2story_metadata"]
    if meta["proposed_goal"]:
        message = prompt.GOAL_PROPOSED_PROMPT.format(goal=meta["proposed_goal"])
    else:
        message = prompt.GOAL_MISSING_PROMPT.format(
            statement=meta["context"].get("statement_of_need", "(not captured yet)")
        )
    if meta["response_feedback"]:
        message = meta["response_feedback"] + "\n\n" + message

    # do not mutate state before interrupt(): this node restarts when resumed
    response = get_user_input(prompt=message)
    if not isinstance(response, str):
        raise ValueError("The goal response must be text.")

    goal, feedback = "", ""
    if _is_approve(response) and meta["proposed_goal"]:
        goal = meta["proposed_goal"]
    elif response.strip() and not _is_approve(response):
        goal = " ".join(response.split())
    else:
        feedback = prompt.GOAL_EMPTY_FEEDBACK
    return {
        "goal2story_metadata": {
            **meta,
            "goal": goal,
            "goal_confirmed": bool(goal),
            "latest_user_response": response,
            "response_feedback": feedback,
        }
    }


def goal_confirmed(state: AgentState) -> bool:
    return state["goal2story_metadata"]["goal_confirmed"]


# generation: the four Goal2Story agents
# -----------------------------------------------------------------------------

def _generation_messages(meta, level, task, trace=()):
    return [
        SystemMessage(content=prompt.GENERATE_INSTRUCTIONS[level]),
        HumanMessage(content=prompt.GENERATE_TASK_TEMPLATE.format(
            **_ref_info(meta, trace), task=task
        )),
    ]


def generate_actors(state: AgentState) -> AgentState:
    """Alpha Captain (Product Owner): who can help reach the goal."""
    meta = _copy_meta(state)
    n = meta["n_per_parent"]
    task = prompt.ACTORS_TASK.format(n=n)
    result = _call(ActorList, _generation_messages(meta, "actors", task))
    meta["actors"] = [
        _make_item(meta, "actors", None, a.model_dump()) for a in result.actors[:n]
    ]
    return {"goal2story_metadata": meta}


def _generate_children(state, level, schema, task_template, list_field):
    """Run one agent per approved parent, as the paper does, one branch at a time."""
    meta = _copy_meta(state)
    n = meta["n_per_parent"]
    children = []
    for parent in meta[PARENT[level]]:
        trace = [*_chain(meta, parent), parent]
        task = task_template.format(n=n, parent_id=parent["id"])
        result = _call(schema, _generation_messages(meta, level, task, trace))
        generated = getattr(result, list_field)[:n] if list_field else [result]
        children.extend(
            _make_item(meta, level, parent["id"], g.model_dump()) for g in generated
        )
    meta[level] = children
    return {"goal2story_metadata": meta}


def generate_impacts(state: AgentState) -> AgentState:
    """Intelligence Officer (Business Analyst): what each actor should do differently."""
    return _generate_children(state, "impacts", ImpactList, prompt.IMPACTS_TASK, "impacts")


def generate_deliverables(state: AgentState) -> AgentState:
    """Delivery Coordinator (Scrum Master): how the software supports each impact."""
    return _generate_children(
        state, "deliverables", DeliverableList, prompt.DELIVERABLES_TASK, "deliverables"
    )


def generate_stories(state: AgentState) -> AgentState:
    """Tactical Officer (Product Owner): one user story per deliverable."""
    return _generate_children(state, "stories", GeneratedStory, prompt.STORY_TASK, None)


# INVEST check
# -----------------------------------------------------------------------------

def check_invest(state: AgentState) -> AgentState:
    """Check each new or changed story against INVEST. Warnings do not block approval."""
    meta = _copy_meta(state)
    for story in meta["stories"]:
        if story["invest"] is not None:
            continue
        request = prompt.INVEST_REQUEST_TEMPLATE.format(
            **_ref_info(meta, _chain(meta, story)), story=_json(_public(story))
        )
        result = _call(InvestCheck, [
            SystemMessage(content=prompt.INVEST_INSTRUCTIONS),
            HumanMessage(content=request),
        ])
        failed = set(result.failed_criteria)
        questions = [q.strip() for q in result.open_questions if q.strip()]
        story["invest"] = {
            "failed_criteria": [c for c in INVEST_ORDER if c in failed],
            "feedback": result.feedback.strip(),
            "open_questions": questions if "testable" in failed else [],
        }
    return {"goal2story_metadata": meta}


# review gates
# -----------------------------------------------------------------------------

def _render_item(meta, level, item) -> str:
    if level == "actors":
        known = {_name(s["name"]) for s in meta["context"].get("confirmed_stakeholders", [])}
        note = ""
        if known and _name(item["stakeholder"]) not in known:
            note = prompt.UNKNOWN_STAKEHOLDER_NOTE
        return (f"- **{item['id']} {item['name']}**: {item['description']} "
                f"(stakeholder: {item['stakeholder']}){note}")
    if level == "stories":
        lines = [f"- **{item['id']}** {item['text']}"]
        invest = item.get("invest")
        if invest and invest["failed_criteria"]:
            lines.append(f"  ⚠ INVEST: {', '.join(invest['failed_criteria'])}. {invest['feedback']}")
        for question in (invest or {}).get("open_questions", []):
            lines.append(f"  ? {question}")
        return "\n".join(lines)
    return f"- **{item['id']}** {item['description']}"


def _parent_heading(meta, parent) -> str:
    chain = [*_chain(meta, parent), parent]
    parts = [p.get("name") or p.get("description") for p in chain]
    return f"Under {parent['id']} ({' → '.join(parts)}):"


def _render_level(meta, level) -> str:
    if not meta[level]:
        return prompt.NO_CHILDREN_NOTE
    if PARENT[level] is None:
        return "\n".join(_render_item(meta, level, i) for i in meta[level])
    sections = []
    for parent in meta[PARENT[level]]:
        children = [i for i in meta[level] if i["parent_id"] == parent["id"]]
        body = "\n".join(_render_item(meta, level, i) for i in children) or prompt.NO_CHILDREN_NOTE
        sections.append(f"{_parent_heading(meta, parent)}\n{body}")
    return "\n\n".join(sections)


def _review_route(meta, level) -> str:
    response = meta["latest_user_response"]
    if _is_approve(response):
        return "approved" if meta[level] else "retry"
    return "revise" if response.strip() else "retry"


def _make_review(level):
    def review(state: AgentState) -> AgentState:
        meta = state["goal2story_metadata"]
        info = prompt.LEVEL_INFO[level]
        feedback = f"\n{meta['response_feedback']}\n" if meta["response_feedback"] else ""
        message = prompt.REVIEW_PROMPT.format(
            title=info["title"], goal=meta["goal"], explanation=info["explanation"],
            items=_render_level(meta, level), feedback=feedback, example=info["example"],
        )
        # do not mutate state before interrupt(): this node restarts when resumed
        response = get_user_input(prompt=message)
        if not isinstance(response, str):
            raise ValueError("The review response must be text.")

        updated = {**meta, "latest_user_response": response, "response_feedback": ""}
        route = _review_route(updated, level)
        if route == "retry":
            updated["response_feedback"] = prompt.EMPTY_LEVEL_FEEDBACK.format(level=level)
        elif route == "approved":
            updated["approved_levels"] = [*meta["approved_levels"], level]
        return {"goal2story_metadata": updated}

    review.__name__ = f"review_{level}"
    review.__doc__ = f"Review gate: the engineer approves or asks for changes to the {level}."
    return review


def make_review_router(level):
    def route(state: AgentState) -> str:
        return _review_route(state["goal2story_metadata"], level)
    return route


review_actors = _make_review("actors")
review_impacts = _make_review("impacts")
review_deliverables = _make_review("deliverables")
review_stories = _make_review("stories")


# revision: apply the engineer's requested changes
# -----------------------------------------------------------------------------

def _apply_revision(meta, level, result) -> tuple[list[str], dict]:
    """Apply explicit operations. Invalid ones are skipped and reported, not fatal."""
    items = {i["id"]: i for i in meta[level]}
    parents = {p["id"] for p in meta[PARENT[level]]} if PARENT[level] else set()
    problems, changes = [], {"updated": [], "added": [], "removed": []}

    for item_id in dict.fromkeys(result.removed_ids):
        if items.pop(item_id, None) is None:
            problems.append(f"Could not remove {item_id}: no such item.")
        else:
            changes["removed"].append(item_id)

    for update in result.updates:
        fields = update.model_dump()
        if any(not str(fields[f]).strip() for f in FIELDS[level]):
            problems.append(f"Skipped a change to {update.id or 'a new item'}: a field was empty.")
            continue
        if update.id is None:
            parent_id = fields.get("parent_id")
            if PARENT[level] and parent_id not in parents:
                problems.append(f"Could not add an item under {parent_id}: no such parent.")
                continue
            item = _make_item(meta, level, parent_id, fields)
            items[item["id"]] = item
            changes["added"].append(item["id"])
        elif update.id in items:
            # an item keeps its parent: its ID shows where it came from
            item = {**items[update.id], **{f: fields[f].strip() for f in FIELDS[level]}}
            if level == "stories":
                item["text"] = _story_text(item)
                item["invest"] = None  # changed stories are checked again
            items[update.id] = item
            changes["updated"].append(update.id)
        else:
            problems.append(f"Could not change {update.id}: no such item.")

    meta[level] = list(items.values())
    return problems, changes


def _make_revise(level):
    def revise(state: AgentState) -> AgentState:
        meta = _copy_meta(state)
        parents = [_public(p) for p in meta[PARENT[level]]] if PARENT[level] else []
        request = prompt.REVISION_REQUEST_TEMPLATE.format(
            **_ref_info(meta),
            parents=_json(parents) if parents else "(none: actors are the top level)",
            level=level,
            items=_json([_public(i) for i in meta[level]]),
            request=meta["latest_user_response"],
        )
        result = _call(REVISION_SCHEMA[level], [
            SystemMessage(content=prompt.REVISION_INSTRUCTIONS[level]),
            HumanMessage(content=request),
        ])
        problems, changes = _apply_revision(meta, level, result)
        notes = [result.clarification_feedback.strip(), *problems]
        meta["response_feedback"] = "\n".join(n for n in notes if n)
        meta["edit_log"] = [*meta["edit_log"], {
            "level": level, "request": meta["latest_user_response"], **changes,
        }]
        return {"goal2story_metadata": meta}

    revise.__name__ = f"revise_{level}"
    revise.__doc__ = f"Apply the engineer's requested changes to the {level}."
    return revise


revise_actors = _make_revise("actors")
revise_impacts = _make_revise("impacts")
revise_deliverables = _make_revise("deliverables")
revise_stories = _make_revise("stories")


# hand-off to lane 4 (clarify & model)
# -----------------------------------------------------------------------------

def finalize_goal2story(state: AgentState) -> AgentState:
    """Expose approved stories with their full trace; storage is deferred."""
    meta = _copy_meta(state)
    if meta["approved_levels"] != list(LEVELS):
        raise ValueError("Every Goal2Story level requires explicit approval.")

    stories, questions = [], []
    for story in meta["stories"]:
        chain = _chain(meta, story)
        stories.append({**story, "goal": meta["goal"], "trace": [i["id"] for i in chain]})
        for question in story["invest"]["open_questions"]:
            questions.append({
                "id": f"Q-{len(questions) + 1}", "story_id": story["id"], "question": question,
            })
    meta["finalized_stories"] = stories
    meta["open_questions"] = questions
    return {"goal2story_metadata": meta}
