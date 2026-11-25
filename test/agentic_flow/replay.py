"""Test fixture: replay recorded model responses so the pipeline runs without a model.

The canned responses are what the model returned for the campus food bank PRD
(src/food_bank_prd.txt). They are raw model output: the real nodes still number
the items, check every quote against the PRD and red-flag what they cannot trace,
exactly as in a live run. Only the model call is replaced.
"""
import json
import os
import socket
import time
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from agentic_flow.capture_intent.context_expected_benefits_current_situation import (
    node as context_node,
)
from agentic_flow.capture_intent.sson import node as sson_node
from agentic_flow.goal2story import node as goal2story_node
from agentic_flow.goal2story.schema import InvestCheck, StoryList
from agentic_flow.goals import node as goal_node
from agentic_flow.impact_analysis import node as impact_node
from agentic_flow.use_cases import node as use_case_node
from agentic_flow.user_modelling.personas import node as persona_node
from agentic_flow.user_modelling.stakeholders import node as stakeholder_node

SAMPLE_PRD = """Campus Food Bank Pickup Scheduler

The McMaster Student Union food bank needs students to book a pickup time slot
online, so that the food bank can serve more students each week without long
lines, and so that it wastes less perishable food.

Today, the food bank runs on walk-ins. Students line up outside the room in the
student centre during its open hours, Tuesday and Thursday from 12 to 3 pm.
Volunteers check each student's ID by hand and pack a hamper while the student
waits. Volunteers track inventory on paper sheets taped to the shelves.

Lines often reach 40 minutes, and some students leave before they are served.
Volunteers cannot predict how many students will come, so they over-pack fresh
produce, and about 30 kg of produce is thrown out every week. Students with
classes during open hours cannot use the food bank at all. Some students say
they feel embarrassed waiting in a visible line.

The scheduler should let students book a 15-minute pickup slot from their phone
and receive a reminder an hour before. Volunteers should see the next day's
bookings so they can pack hampers in advance. The food bank wants to cut average
wait time to under 5 minutes, reduce produce waste to under 10 kg a week, and
serve at least 25% more students per week within one term.

We expect more students to use the food bank and fewer to skip meals before
exams. Volunteer shifts will move from packing on demand to packing in batches.

The food bank must stay anonymous: no record may link a student's name to their
visits. It will always operate only from its room in the student centre, and it
will always serve walk-ins who did not book.

Everyone signs in with their MacID. The system must run on the MSU's existing
web hosting, and it must be ready before the January term starts. Food
donations, delivery to residences, and the volunteer sign-up process are
outside the scope of this project.

Volunteers are mostly first-year students who work one 3-hour shift a week and
are not comfortable with technical tools. The MSU vice-president of services
approves the food bank's budget and wants a usage report each term.
"""

_TARGETS = "The food bank wants to cut average wait time to under 5 minutes, reduce produce waste to under 10 kg a week, and serve at least 25% more students per week within one term."
_CONSTRAINT = "The system must run on the MSU's existing web hosting, and it must be ready before the January term starts."


def _criterion() -> dict:
    return {"verdict": "met", "reason": "The statement covers this criterion."}


RESPONSES: dict[str, dict] = {
    "sson": {
        "stated_sson": None,
        "synthesized_sson": (
            "The McMaster Student Union food bank needs a pickup scheduler to reduce wait "
            "times, minimize food waste, and increase student usage, by allowing students "
            "to book pickup slots online and enabling volunteers to prepare hampers in "
            "advance. This will help the food bank serve more students efficiently and "
            "anonymously."
        ),
        "evidence": [
            "The McMaster Student Union food bank needs students to book a pickup time slot online, so that the food bank can serve more students each week without long lines, and so that it wastes less perishable food.",
            "The scheduler should let students book a 15-minute pickup slot from their phone and receive a reminder an hour before. Volunteers should see the next day's bookings so they can pack hampers in advance.",
            _TARGETS,
        ],
        "what": "reduce wait times, minimize food waste, and increase student usage",
        "how": "allow students to book pickup slots online and enable volunteers to prepare hampers in advance",
        "why": "to help the food bank serve more students efficiently and anonymously",
        "success_measure": "cut average wait time to under 5 minutes, reduce produce waste to under 10 kg a week, and serve at least 25% more students per week within one term",
        "context_and_objective": (
            "The food bank needs a pickup scheduler to improve efficiency and reduce waste, "
            "as lines often reach 40 minutes, and about 30 kg of produce is thrown out every "
            "week. The scheduler will help the food bank serve more students and reduce wait "
            "times, with the goal of more students using the food bank and fewer skipping "
            "meals before exams."
        ),
    },
    "evaluation": {
        "criteria": {
            "clear_and_concise": _criterion(),
            "goal_and_how": _criterion(),
            "names_capability": _criterion(),
            "need_not_want": {"verdict": "partially_met",
                              "reason": "It names the scheduler before the need it serves."},
            "success_condition": _criterion(),
        },
        "feedback": (
            "The SSON is strong and clear. Lead with the need (shorter waits, less waste) "
            "rather than the scheduler, and add the deadline the PRD gives ('before the "
            "January term starts') to sharpen the success condition."
        ),
    },
    "situation": {
        "current_situation": (
            "Today, the food bank runs on walk-ins. Students line up outside the room in the "
            "student centre during its open hours, Tuesday and Thursday from 12 to 3 pm. "
            "Volunteers check each student's ID by hand and pack a hamper while the student "
            "waits. Volunteers track inventory on paper sheets taped to the shelves."
        ),
        "problems": [
            {"description": "Lines often reach 40 minutes, and some students leave before they are served.",
             "source": "Lines often reach 40 minutes, and some students leave before they are served."},
            {"description": "Volunteers cannot predict how many students will come, so they over-pack fresh produce, and about 30 kg of produce is thrown out every week.",
             "source": "Volunteers cannot predict how many students will come, so they over-pack fresh produce, and about 30 kg of produce is thrown out every week."},
            {"description": "Students with classes during open hours cannot use the food bank at all.",
             "source": "Students with classes during open hours cannot use the food bank at all."},
            {"description": "Some students say they feel embarrassed waiting in a visible line.",
             "source": "Some students say they feel embarrassed waiting in a visible line."},
        ],
    },
    "benefits": {
        "benefits": [
            {"description": "cut average wait time to under 5 minutes", "source": _TARGETS,
             "addresses": ["Problem-1"], "measure": "under 5 minutes"},
            {"description": "reduce produce waste to under 10 kg a week", "source": _TARGETS,
             "addresses": ["Problem-2"], "measure": "under 10 kg a week"},
            {"description": "serve at least 25% more students per week within one term",
             "source": _TARGETS, "addresses": ["Problem-3"],
             "measure": "at least 25% more students per week"},
            {"description": "volunteer shifts will move from packing on demand to packing in batches",
             "source": "Volunteer shifts will move from packing on demand to packing in batches.",
             "addresses": [], "measure": None},
        ],
        "out_of_scope_problems": [],
    },
    "environment": {
        "effects": [
            {"description": "more students to use the food bank and fewer to skip meals before exams",
             "source": "We expect more students to use the food bank and fewer to skip meals before exams."},
        ],
        "invariants": [
            {"description": "no record may link a student's name to their visits",
             "source": "The food bank must stay anonymous: no record may link a student's name to their visits."},
            {"description": "it will always operate only from its room in the student centre",
             "source": "It will always operate only from its room in the student centre"},
            {"description": "it will always serve walk-ins who did not book",
             "source": "it will always serve walk-ins who did not book"},
        ],
        "constraints": [
            {"description": "Everyone signs in with their MacID.",
             "source": "Everyone signs in with their MacID."},
            {"description": "run on the MSU's existing web hosting", "source": _CONSTRAINT},
            {"description": "ready before the January term starts", "source": _CONSTRAINT},
        ],
        "scope_exclusions": [
            {"description": "food donations, delivery to residences, and the volunteer sign-up process are outside the scope of this project",
             "source": "Food donations, delivery to residences, and the volunteer sign-up process are outside the scope of this project."},
        ],
    },
    "stakeholders": {
        "stakeholders": [
            {"name": "Students using the food bank", "involvement": "direct",
             "summary": "Students who book pickup slots and collect hampers.",
             "justification": "The PRD says students book a 15-minute pickup slot from their phone."},
            {"name": "Food bank volunteers", "involvement": "direct",
             "summary": "Volunteers who check IDs, pack hampers and track inventory.",
             "justification": "Volunteers should see the next day's bookings so they can pack hampers in advance."},
            {"name": "McMaster Student Union food bank", "involvement": "direct",
             "summary": "The organization that runs the food bank and owns the scheduler.",
             "justification": "The PRD opens with the food bank's need for online booking."},
            {"name": "MSU vice-president of services", "involvement": "indirect",
             "summary": "Approves the food bank's budget and reviews usage.",
             "justification": "The PRD says this role approves the budget and wants a usage report each term."},
        ],
    },
    "personas": {
        "personas": [
            {"stakeholder_id": "Stakeholder-1", "name": "", "role": "Student who uses the food bank",
             "status_and_trust_level": "", "demographics": "",
             "ksa": "Books slots from their phone.",
             "gmc": "Wants to pick up food without a long, visible line; some have classes during open hours.",
             "usage_patterns": "Books a 15-minute pickup slot and gets a reminder an hour before; open hours are Tuesday and Thursday 12 to 3 pm."},
            {"stakeholder_id": "Stakeholder-2", "name": "", "role": "Food bank volunteer",
             "status_and_trust_level": "", "demographics": "Mostly first-year students.",
             "ksa": "Not comfortable with technical tools.",
             "gmc": "Wants to pack hampers in advance instead of while students wait.",
             "usage_patterns": "Works one 3-hour shift a week; checks the next day's bookings."},
            {"stakeholder_id": "Stakeholder-4", "name": "", "role": "MSU vice-president of services",
             "status_and_trust_level": "Approves the food bank's budget.", "demographics": "",
             "ksa": "", "gmc": "Wants a usage report each term.",
             "usage_patterns": "Reviews usage once a term."},
        ],
    },
    "goals": {
        "goals": [
            {"statement": "Cut average wait time to under 5 minutes", "goal_type": "hard",
             "source": _TARGETS, "benefit_ids": ["Benefit-1"],
             "actors": [
                 {"name": "Students", "stakeholder_id": "Stakeholder-1", "role": "Food bank user",
                  "involvement": "Book a pickup slot instead of lining up."},
                 {"name": "Volunteers", "stakeholder_id": "Stakeholder-2", "role": "Hamper packer",
                  "involvement": "Pack hampers in advance from the next day's bookings."}],
             "resources": ["pickup slot bookings", "next day's booking list"],
             "plans": "Students book a 15-minute pickup slot from their phone and get a reminder an hour before; volunteers pack hampers in advance from the next day's bookings.",
             "justification": "Lines often reach 40 minutes, and some students leave before they are served."},
            {"statement": "Reduce produce waste to under 10 kg a week", "goal_type": "hard",
             "source": _TARGETS, "benefit_ids": ["Benefit-2"],
             "actors": [{"name": "Volunteers", "stakeholder_id": "Stakeholder-2", "role": "Hamper packer",
                         "involvement": "Pack only what the next day's bookings need."}],
             "resources": ["next day's booking list", "inventory sheets"], "plans": "",
             "justification": "About 30 kg of produce is thrown out every week."},
            {"statement": "Serve at least 25% more students per week within one term",
             "goal_type": "hard", "source": _TARGETS, "benefit_ids": ["Benefit-3"],
             "actors": [{"name": "McMaster Student Union food bank", "stakeholder_id": "Stakeholder-3",
                         "role": "Service provider", "involvement": "Serves more students each week."}],
             "resources": [], "plans": "", "justification": "Students with classes during open hours cannot use the food bank at all."},
            {"statement": "Students feel comfortable picking up food", "goal_type": "soft",
             "source": "", "benefit_ids": [],
             "actors": [{"name": "Students", "stakeholder_id": "Stakeholder-1", "role": "Food bank user",
                         "involvement": "Avoid waiting in a visible line."}],
             "resources": [], "plans": "", "justification": "Some students say they feel embarrassed waiting in a visible line."},
            {"statement": "Give the MSU vice-president of services a usage report each term",
             "goal_type": "hard",
             "source": "The MSU vice-president of services approves the food bank's budget and wants a usage report each term.",
             "benefit_ids": [],
             "actors": [{"name": "MSU vice-president of services", "stakeholder_id": "Stakeholder-4",
                         "role": "Budget approver", "involvement": "Reviews usage each term."}],
             "resources": ["usage report"], "plans": "", "justification": "They approve the food bank's budget."},
        ],
    },
    "use_cases": {
        "system_name": "Food Bank Pickup Scheduler",
        "actors": [
            {"name": "Student", "kind": "human", "stakeholder_id": "Stakeholder-1"},
            {"name": "Volunteer", "kind": "human", "stakeholder_id": "Stakeholder-2"},
            {"name": "MSU vice-president of services", "kind": "human",
             "stakeholder_id": "Stakeholder-4"},
            {"name": "MacID sign-in service", "kind": "system", "stakeholder_id": None},
        ],
        "use_cases": [
            {"name": "Book pickup slot", "description": "A student books a 15-minute pickup slot from their phone.",
             "primary_actor": "Student", "supporting_actors": ["MacID sign-in service"],
             "goal_ids": ["Goal-1", "Goal-3"]},
            {"name": "Receive pickup reminder", "description": "A student gets a reminder an hour before their slot.",
             "primary_actor": "Student", "supporting_actors": [], "goal_ids": ["Goal-1"]},
            {"name": "Pack hampers in advance", "description": "Volunteers pack hampers for the next day's bookings.",
             "primary_actor": "Volunteer", "supporting_actors": [], "goal_ids": ["Goal-1", "Goal-2"]},
            {"name": "View next day's bookings", "description": "Volunteers see the next day's bookings.",
             "primary_actor": "Volunteer", "supporting_actors": [], "goal_ids": ["Goal-2"]},
            {"name": "Hand out hamper", "description": "A volunteer hands a packed hamper to the student at pickup.",
             "primary_actor": "Volunteer", "supporting_actors": ["Student"], "goal_ids": ["Goal-1", "Goal-3"]},
            {"name": "Serve walk-in student", "description": "A volunteer serves a student who did not book.",
             "primary_actor": "Volunteer", "supporting_actors": [], "goal_ids": ["Goal-3"]},
            {"name": "Produce term usage report", "description": "The vice-president gets the food bank's usage for the term.",
             "primary_actor": "MSU vice-president of services", "supporting_actors": [], "goal_ids": ["Goal-5"]},
        ],
        "relationships": [
            {"kind": "include", "source": "Pack hampers in advance", "target": "View next day's bookings",
             "condition": ""},
            {"kind": "extend", "source": "Serve walk-in student", "target": "Hand out hamper",
             "condition": "if the student did not book"},
        ],
    },
}

def impact_reply(messages) -> dict:
    """Impact analysis has no fixed answer: revise the first linked artifact that has
    a text field, call the rest unaffected."""
    text = messages[-1].content
    candidates = json.loads(text.split("<candidates>", 1)[1].split("</candidates>", 1)[0])
    assessments, revised = [], False
    for c in candidates:
        fields = [f for f, v in c["revisable_fields"].items() if isinstance(v, str) and v]
        if fields and not revised:
            revised = True
            old = c["revisable_fields"][fields[0]]
            assessments.append({"artifact_id": c["id"], "verdict": "revise",
                                "reason": "The edit changes what this artifact relies on.",
                                "changes": [{"field": fields[0],
                                             "value": f"{old} (checked against the edit)"}]})
        else:
            assessments.append({"artifact_id": c["id"], "verdict": "unaffected",
                                "reason": "The edit does not touch what this states."})
    return {"assessments": assessments, "new_artifacts": []}


RESPONSES["impact"] = impact_reply
RESPONSES["stories"] = {"stories": [
    {"actor": "Students", "action": "book a pickup slot from my phone",
     "expected_outcome": "I do not wait in a long line"}]}
RESPONSES["invest"] = {"failed_criteria": [], "feedback": "", "open_questions": []}
# goal2story makes its models per schema (node._model), not as module attributes
_GOAL2STORY_KEYS = {StoryList: "stories", InvestCheck: "invest"}

# module attribute -> canned response key
_TARGET_MODELS = {
    (sson_node, "sson_extractor"): "sson",
    (sson_node, "sson_evaluator"): "evaluation",
    (context_node, "situation_extractor"): "situation",
    (context_node, "benefit_extractor"): "benefits",
    (context_node, "environment_extractor"): "environment",
    (stakeholder_node, "stakeholder_extractor"): "stakeholders",
    (persona_node, "persona_extractor"): "personas",
    (goal_node, "goal_extractor"): "goals",
    (use_case_node, "use_case_extractor"): "use_cases",
    (impact_node, "impact_model"): "impact",
}


class _ReplayModel:
    """Stands in for `model.with_structured_output(...)`: returns the recording."""

    def __init__(self, key: str, delay: float):
        self.key, self.delay = key, delay

    def invoke(self, _messages):
        time.sleep(DELAY_SECONDS if self.delay is None else self.delay)
        reply = RESPONSES[self.key]
        return reply(_messages) if callable(reply) else reply


DELAY_SECONDS = float(os.environ.get("IDE3_REPLAY_DELAY", "0"))


def _no_network(self, address, *args, **kwargs):
    raise RuntimeError(f"A test tried to reach {address}: every model call must be replayed.")


@contextmanager
def replay_models(delay: float | None = None):
    with ExitStack() as stack:
        for (module, name), key in _TARGET_MODELS.items():
            stack.enter_context(patch.object(module, name, _ReplayModel(key, delay)))
        stack.enter_context(patch.object(
            goal2story_node, "_model", lambda schema: _ReplayModel(_GOAL2STORY_KEYS[schema], delay)))
        # anything not replayed above would reach a real model: fail loudly instead
        stack.enter_context(patch.object(socket.socket, "connect", _no_network))
        yield
