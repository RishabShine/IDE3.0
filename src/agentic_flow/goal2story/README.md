# Goal2Story (lane 3)

Breaks one confirmed goal into user stories through automated impact mapping,
following Goal2Story (arXiv:2503.13279, §3), with IDE3.0 review gates added.
The outer IDE3.0 graph runs SSON capture, then user modelling, then this
graph, then END. It can also run on its own for testing.

| Level | Agent (paper profile) | Question | IDs |
|---|---|---|---|
| Actors | Alpha Captain (Product Owner) | **Who** can help or block the goal? | `A-1`, `A-2` |
| Impacts | Intelligence Officer (Business Analyst) | **What** should each actor do differently? | `I-1.1`, `I-1.2` |
| Deliverables | Delivery Coordinator (Scrum Master) | **How** does the software support each impact? | `D-1.1.1` |
| Stories | Tactical Officer (Product Owner) | One user story per deliverable | `US-1` … |

## Flow

```text
initialize → confirm goal → generate actors → review ⇄ revise
                          → generate impacts → review ⇄ revise
                          → generate deliverables → review ⇄ revise
                          → generate stories → INVEST check → review ⇄ revise (→ INVEST check)
                          → finalize → END
```

- **Goal confirmation.** The first goal in `captured_intent["goals"]` is
  proposed; the engineer enters APPROVE or types a different goal. Lane 1
  does not capture goals yet, so without one the engineer is asked for it.
- **Generation.** As in the paper, each agent runs once per approved parent
  and sees the Ref Info: the context anchors (SSON, project context, captured
  intent, confirmed stakeholders), the goal, and the items above it on its
  branch. `n_per_parent` (default 2, the paper's value) caps each call, so the
  default run gives 2 × 2 × 2 = 8 stories.
- **Review gates (ours).** After each level the engineer enters APPROVE or
  describes changes in plain language ("remove I-1.2", "add an impact for
  A-2: ..."). A model call turns that into explicit operations (updates,
  additions, removals). Untouched items keep their IDs, new items get new IDs,
  and invalid operations are skipped and shown to the engineer rather than
  crashing the run. Every change is recorded in `edit_log`. A level with no
  items cannot be approved.
- **Actors from stakeholders.** The Alpha Captain picks actors from
  `stakeholder_metadata["finalized_stakeholders"]`. An actor that does not
  match a confirmed stakeholder is flagged in the review.
- **INVEST check (3RA3 L24).** Each new or changed story is checked once.
  Failures are shown as warnings and do not block approval. When a story is
  not testable, the questions needed to make it testable become
  `open_questions` for lane 4.
- **Format Doctor.** Every model call uses Ollama's JSON schema mode. If the
  reply still fails to parse or validate, the call is retried once with a
  repair prompt. A second failure raises, and the last checkpoint is kept.

Each level is generated only after the one above is approved, so editing an
earlier level after approval (with "needs review" marking) is not supported yet.

## Output for lane 4

After approval, `result["goal2story_metadata"]` contains:

- `finalized_stories`: each story has `id`, `parent_id`, `actor`, `action`,
  `expected_outcome`, `text` ("As a …, I want to …, so that …"), `invest`,
  `goal` and `trace` (e.g. `["A-1", "I-1.1", "D-1.1.2"]`).
- `open_questions`: `[{"id": "Q-1", "story_id": "US-2", "question": "..."}]`.
- `actors`, `impacts`, `deliverables`, `stories`: the full approved impact map.

Persistent artifact IDs and saving to the project remain to be connected.
Personas are not used yet; when lane 2 provides them, add them to `context`
in `initialize_goal2story` and the stories can use the persona's name.

## Run it

With `src` on the Python import path and Ollama running the configured model:

```python
from langgraph.types import Command
from agentic_flow.goal2story.graph import goal2story_graph

config = {"configurable": {"thread_id": "project-1-goal2story"}}
result = goal2story_graph.invoke(upstream_state, config)

# The UI displays result["__interrupt__"][0].value["prompt_to_user"].
# Resume the same graph and thread with the user's text, repeating as needed.
result = goal2story_graph.invoke(Command(resume=user_reply), config)
```

To try it in the terminal with the study-room example (from `src`):

```sh
python -m agentic_flow.goal2story.demo          # sample lane 1 and 2 output
python -m agentic_flow.goal2story.demo --n 1    # quick run: one story
python -m agentic_flow.goal2story.demo --full   # whole IDE3.0 flow
IDE3_MODEL=qwen2.5:7b python -m agentic_flow.goal2story.demo
```

`IDE3_MODEL` overrides the default model in `core/models.py`. In the paper,
Qwen2.5-7B scored much higher on story quality than Llama2-7B (97% vs 54%).

## Tests

From the repository root:

```sh
PYTHONPATH=src python -m unittest discover -s test/agentic_flow -v
```

`test/agentic_flow/test_goal2story.py` uses stub models, so it runs without
Ollama while exercising real graph transitions, interrupts and checkpoints.
It covers the full 2 × 2 × 2 run, IDs and traces, revisions, invalid
operations, INVEST hand-off, the Format Doctor and the full IDE3.0 flow.
The repository needs Python 3.11 or newer (`typing.NotRequired`).
