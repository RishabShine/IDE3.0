"""Goal2Story: user stories for every goal the goals stage extracted.

The goals, their actors, resources and plans come from state["goal_metadata"];
nothing is generated here except the stories. One model call per goal writes
its stories, each story gets an INVEST check, and in review mode the engineer
approves or revises them. With a PRD in the state (PRD mode) it runs straight
through.
"""
import json
import re
from functools import cache

from langchain_core.messages import HumanMessage, SystemMessage

from agentic_flow.core.models import base_model
from agentic_flow.core.shared_nodes import get_user_input
from agentic_flow.goal2story import prompt
from agentic_flow.goal2story.schema import InvestCheck, StoryList, StoryRevision
from agentic_flow.state import RED_FLAG, AgentState

DEFAULT_STORIES_PER_GOAL = 3
FIELDS = ("actor", "action", "expected_outcome")
INVEST_ORDER = ("independent", "negotiable", "valuable", "estimable", "small", "testable")


# helpers
# -----------------------------------------------------------------------------

def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _name(value: str | None) -> str:
    return " ".join((value or "").split()).casefold()


def _unflag(text: str | None) -> str:
    return re.sub(rf"^{RED_FLAG}\s*", "", (text or "").strip())


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


def _article(noun: str) -> str:
    lower = noun.lower()
    # "As Students, ..." reads better than "As a Students, ..."
    if lower.startswith(("a ", "an ", "the ")) or (lower.endswith("s") and not lower.endswith("ss")):
        return noun
    return ("an " if noun[:1].lower() in "aeiou" else "a ") + noun


def _story_text(story) -> str:
    action = story["action"].strip().rstrip(".")
    if action.lower().startswith("to "):
        action = action[3:]
    outcome = story["expected_outcome"].strip().rstrip(".")
    return f"As {_article(story['actor'].strip())}, I want to {action}, so that {outcome}."


def _public(story) -> dict:
    """The fields the model sees for a story (no internal bookkeeping)."""
    return {k: v for k, v in story.items() if k not in ("invest", "text", "stakeholder_id")}


def _goals_by_id(meta) -> dict[str, dict]:
    return {goal["id"]: goal for goal in meta["goals"]}


def _stakeholder_of(goal: dict, actor: str) -> str | None:
    """The stakeholder behind the story's actor, through the goal's actor list."""
    for goal_actor in goal.get("actors") or []:
        if _name(goal_actor.get("name")) == _name(actor):
            return goal_actor.get("stakeholder_id")
    return None


def _make_story(meta, goal_id: str, fields: dict) -> dict:
    number = meta["next_index"]
    meta["next_index"] = number + 1
    story = {"id": f"US-{number}", "parent_id": goal_id}
    story.update({f: fields[f].strip() for f in FIELDS})
    story["stakeholder_id"] = _stakeholder_of(_goals_by_id(meta)[goal_id], story["actor"])
    story["text"] = _story_text(story)
    story["invest"] = None
    return story


def _copy_meta(state) -> dict:
    meta = state["goal2story_metadata"]
    return {**meta, "stories": [dict(s) for s in meta["stories"]]}


def _goal_view(goal: dict, benefits: list[dict]) -> dict:
    """A goal as the story agent sees it, with the benefits it delivers spelled out."""
    delivered = [
        {"id": b["id"], "description": _unflag(b.get("description")), "measure": b.get("measure")}
        for b in benefits if b["id"] in (goal.get("benefit_ids") or [])
    ]
    return {
        "id": goal["goal_id"],
        "statement": _unflag(goal.get("statement")),
        "goal_type": goal.get("goal_type"),
        "actors": goal.get("actors") or [],
        "resources": goal.get("resources") or [],
        "plans": goal.get("plans") or "",
        "justification": goal.get("justification") or "",
        "delivers_benefits": delivered,
    }


# initialization
# -----------------------------------------------------------------------------

def initialize_goal2story(state: AgentState) -> AgentState:
    """Take the extracted goals and the context anchors, without calling the model.

    With a PRD in the state, Goal2Story runs in PRD mode: the stories are
    accepted as written, with no review stop. Set goal2story_metadata["auto"]
    to override this.
    """
    existing = state.get("goal2story_metadata") or {}
    if existing.get("initialized"):
        return {}

    goals = (state.get("goal_metadata") or {}).get("goals") or []

    prd = (state.get("prd") or "").strip()
    captured = state.get("captured_intent") or {}
    context = {
        "prd": prd,
        "statement_of_need": _unflag(captured.get("single_statement_intent")),
        "stakeholders": (state.get("stakeholder_metadata") or {}).get("stakeholders", []),
        "personas": (state.get("persona_metadata") or {}).get("personas", []),
    }
    benefits = captured.get("benefits") or []

    return {
        "goal2story_metadata": {
            "initialized": True,
            "auto": existing.get("auto", bool(prd)),
            "stories_per_goal": existing.get("stories_per_goal", DEFAULT_STORIES_PER_GOAL),
            "context": {k: v for k, v in context.items() if v},
            "goals": [_goal_view(goal, benefits) for goal in goals],
            "stories": [],
            "next_index": 1,
            "latest_user_response": "",
            "response_feedback": "",
            "approved": False,
            "edit_log": [],
            "open_questions": [],
            "finalized_stories": [],
            # nothing to write stories for: the graph ends here (see has_goals)
            "skipped": not goals,
        }
    }


def has_goals(state: AgentState) -> bool:
    """Route after initialize: no extracted goals means no stories, not an error."""
    return bool(state["goal2story_metadata"]["goals"])


# generation: one story agent call per goal
# -----------------------------------------------------------------------------

def generate_stories(state: AgentState) -> AgentState:
    """Tactical Officer (Product Owner): the user stories that achieve each goal."""
    meta = _copy_meta(state)
    n = meta["stories_per_goal"]
    for goal in meta["goals"]:
        task = prompt.STORY_TASK.format(goal_id=goal["id"], n=n)
        result = _call(StoryList, [
            SystemMessage(content=prompt.STORY_INSTRUCTIONS),
            HumanMessage(content=prompt.GENERATE_TASK_TEMPLATE.format(
                anchors=_json(meta["context"]), goal=_json(goal), task=task,
            )),
        ])
        for generated in result.stories[:n]:
            fields = generated.model_dump()
            if all(fields[f].strip() for f in FIELDS):
                meta["stories"].append(_make_story(meta, goal["id"], fields))
    return {"goal2story_metadata": meta}


# INVEST check
# -----------------------------------------------------------------------------

def check_invest(state: AgentState) -> AgentState:
    """Check each new or changed story against INVEST. Warnings do not block approval."""
    meta = _copy_meta(state)
    goals = _goals_by_id(meta)
    for story in meta["stories"]:
        if story["invest"] is not None:
            continue
        request = prompt.INVEST_REQUEST_TEMPLATE.format(
            anchors=_json(meta["context"]), goal=_json(goals[story["parent_id"]]),
            story=_json(_public(story)),
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


# review gate
# -----------------------------------------------------------------------------

def _render_story(story) -> str:
    lines = [f"- **{story['id']}** {story['text']}"]
    invest = story.get("invest")
    if invest and invest["failed_criteria"]:
        lines.append(f"  ⚠ INVEST: {', '.join(invest['failed_criteria'])}. {invest['feedback']}")
    for question in (invest or {}).get("open_questions", []):
        lines.append(f"  ? {question}")
    return "\n".join(lines)


def _render_stories(meta) -> str:
    sections = []
    for goal in meta["goals"]:
        stories = [s for s in meta["stories"] if s["parent_id"] == goal["id"]]
        body = "\n".join(_render_story(s) for s in stories) or prompt.NO_STORIES_NOTE
        sections.append(f"{goal['id']}: {goal['statement']}\n{body}")
    return "\n\n".join(sections)


def _review_route(meta) -> str:
    if meta.get("auto"):
        return "approved"
    response = meta["latest_user_response"]
    if _is_approve(response):
        return "approved" if meta["stories"] else "retry"
    return "revise" if response.strip() else "retry"


def review_stories(state: AgentState) -> AgentState:
    """Review gate: the engineer approves the stories or asks for changes."""
    meta = state["goal2story_metadata"]
    if meta.get("auto"):
        # PRD mode: accept the stories as written, with no review stop
        return {"goal2story_metadata": {**meta, "approved": True}}
    feedback = f"\n{meta['response_feedback']}\n" if meta["response_feedback"] else ""
    message = prompt.REVIEW_PROMPT.format(items=_render_stories(meta), feedback=feedback)
    # do not mutate state before interrupt(): this node restarts when resumed
    response = get_user_input(prompt=message)
    if not isinstance(response, str):
        raise ValueError("The review response must be text.")

    updated = {**meta, "latest_user_response": response, "response_feedback": ""}
    route = _review_route(updated)
    if route == "retry":
        updated["response_feedback"] = prompt.EMPTY_STORIES_FEEDBACK
    elif route == "approved":
        updated["approved"] = True
    return {"goal2story_metadata": updated}


def route_review(state: AgentState) -> str:
    return _review_route(state["goal2story_metadata"])


# revision: apply the engineer's requested changes
# -----------------------------------------------------------------------------

def _apply_revision(meta, result) -> tuple[list[str], dict]:
    """Apply explicit operations. Invalid ones are skipped and reported, not fatal."""
    stories = {s["id"]: s for s in meta["stories"]}
    goals = _goals_by_id(meta)
    problems, changes = [], {"updated": [], "added": [], "removed": []}

    for story_id in dict.fromkeys(result.removed_ids):
        if stories.pop(story_id, None) is None:
            problems.append(f"Could not remove {story_id}: no such story.")
        else:
            changes["removed"].append(story_id)

    for update in result.updates:
        fields = update.model_dump()
        if any(not str(fields[f]).strip() for f in FIELDS):
            problems.append(f"Skipped a change to {update.id or 'a new story'}: a field was empty.")
            continue
        if update.id is None:
            if fields["parent_id"] not in goals:
                problems.append(f"Could not add a story under {fields['parent_id']}: no such goal.")
                continue
            story = _make_story(meta, fields["parent_id"], fields)
            stories[story["id"]] = story
            changes["added"].append(story["id"])
        elif update.id in stories:
            # a story keeps its goal: its trace starts there
            story = {**stories[update.id], **{f: fields[f].strip() for f in FIELDS}}
            story["stakeholder_id"] = _stakeholder_of(goals[story["parent_id"]], story["actor"])
            story["text"] = _story_text(story)
            story["invest"] = None  # changed stories are checked again
            stories[update.id] = story
            changes["updated"].append(update.id)
        else:
            problems.append(f"Could not change {update.id}: no such story.")

    meta["stories"] = list(stories.values())
    return problems, changes


def revise_stories(state: AgentState) -> AgentState:
    """Apply the engineer's requested changes to the stories."""
    meta = _copy_meta(state)
    request = prompt.REVISION_REQUEST_TEMPLATE.format(
        anchors=_json(meta["context"]),
        goals=_json([{"id": g["id"], "statement": g["statement"]} for g in meta["goals"]]),
        stories=_json([_public(s) for s in meta["stories"]]),
        request=meta["latest_user_response"],
    )
    result = _call(StoryRevision, [
        SystemMessage(content=prompt.REVISION_INSTRUCTIONS),
        HumanMessage(content=request),
    ])
    problems, changes = _apply_revision(meta, result)
    notes = [result.clarification_feedback.strip(), *problems]
    meta["response_feedback"] = "\n".join(n for n in notes if n)
    meta["edit_log"] = [*meta["edit_log"], {"request": meta["latest_user_response"], **changes}]
    return {"goal2story_metadata": meta}


# hand-off to lane 4 (clarify & model)
# -----------------------------------------------------------------------------

def finalize_goal2story(state: AgentState) -> AgentState:
    """Expose approved stories with their goal; storage is deferred."""
    meta = _copy_meta(state)
    if not meta["approved"]:
        raise ValueError("The user stories require explicit approval.")

    goals = _goals_by_id(meta)
    stories, questions = [], []
    for story in meta["stories"]:
        goal = goals[story["parent_id"]]
        stories.append({**story, "goal": goal["statement"],
                        "trace": [goal["id"], *[b["id"] for b in goal["delivers_benefits"]]]})
        for question in story["invest"]["open_questions"]:
            questions.append({
                "id": f"Q-{len(questions) + 1}", "story_id": story["id"], "question": question,
            })
    meta["finalized_stories"] = stories
    meta["open_questions"] = questions
    return {"goal2story_metadata": meta}
