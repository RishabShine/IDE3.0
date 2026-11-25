# Goal2Story (lane 3)

Writes the user stories for every goal the goals stage extracted. The goals,
their actors, resources, plans and delivered benefits come from
`state["goal_metadata"]`; Goal2Story generates nothing but the stories.

The outer IDE3.0 graph starts from `{"prd": ...}` and runs capture intent, user
modelling, goals, then this graph, then the artifact graph. It can also run on
its own for testing, given a state that already holds `goal_metadata`.

```text
initialize → generate stories (one call per goal) → INVEST check
           → review ⇄ revise (→ INVEST check) → finalize → END
```

## Two modes

- **PRD mode** (default when `state["prd"]` is set). The stories are accepted
  as written and the graph runs straight through with no questions.
- **Review mode** (no PRD). The engineer enters APPROVE or describes changes
  ("remove US-3", "add a story for Goal-2: ..."). A model call turns that into
  explicit operations. Untouched stories keep their IDs, new stories get new
  IDs, and invalid operations are skipped and shown rather than crashing the
  run. Every change is recorded in `edit_log`.

Set `goal2story_metadata["auto"]` to `True` or `False` to force a mode, and
`goal2story_metadata["stories_per_goal"]` (default 3) to cap the stories per goal.

## What each step does

- **Initialize.** Takes every goal from `goal_metadata` with the benefits it
  delivers spelled out, plus the context anchors (PRD, SSON, stakeholders,
  personas). No model call. With no extracted goals it sets `skipped` and
  the graph ends without writing stories.
- **Generate stories.** The Tactical Officer (Product Owner) writes the stories
  that achieve one goal, one call per goal. Each story's actor is one of the
  goal's actors; its stakeholder link (`stakeholder_id`) comes from that
  actor, not from the model.
- **INVEST check (3RA3 L24).** Each new or changed story is checked once.
  Failures are shown as warnings and do not block approval. When a story is
  not testable, the questions needed to make it testable become
  `open_questions` for lane 4.
- **Format Doctor.** Every model call uses JSON schema mode. If the reply still
  fails to parse or validate, the call is retried once with a repair prompt. A
  second failure raises, and the last checkpoint is kept.
- **Finalize.** `finalized_stories` holds each approved story with its goal
  statement and `trace`: the goal ID, then the benefits that goal delivers.

## IDs and trace

| Item | ID | Links |
|---|---|---|
| Story | `US-1`, `US-2`, … | `parent_id` = its goal (`Goal-n`); `stakeholder_id` through the goal actor |

`artifacts.py` adds the stories to the artifact graph: *story implements goal*
and *story performed by stakeholder*. Stories are optional there, so a run
without Goal2Story reports no missing-story gap; once stories exist, a goal
with none is reported as `goal_without_story`.

## Run it

```sh
cd src
python -m agentic_flow.goal2story.demo --prd       # PRD mode on the sample goals
python -m agentic_flow.goal2story.demo             # review mode
python -m agentic_flow.goal2story.demo --full      # whole IDE3.0 flow from the PRD
```

Tests stub the model: `PYTHONPATH=src python -m unittest test.agentic_flow.test_goal2story`.
