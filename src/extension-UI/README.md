# IDE3.0 extension UI

A browser UI for the agentic flow, styled after `IDE3.0-wireframe-prototype.html`.
You paste a PRD on the welcome page and the flow fills seven pages. Every artifact
keeps the PRD quote it came from, a review status and a change history.

| Page | What it shows | Produced by |
|------|---------------|-------------|
| Welcome | PRD input, pipeline progress, run log, past sessions | — |
| Capture intent | SSON, what/how/why/success, G.1 context, evidence, L04 evaluation | `capture_intent/sson` |
| Situation & benefits | G.2 current situation, problems, G.3 benefits, effects, invariants, constraints, scope exclusions | `capture_intent/context_…` |
| Stakeholders | Stakeholders and the personas that represent them | `user_modelling/stakeholders` |
| Personas | MSF persona cards linked to stakeholders | `user_modelling/personas` |
| Goals | Hard and soft goals with actors, resources, plans, justification; linked to benefits and stakeholders | `goals` |
| Use cases | Rough use case model drawn in UML notation (3RA3 L13) with a legend, model checks, use case and actor lists. Read-only for now | `use_cases` |
| Trace | Artifact graph with a full legend and type filters, gaps, impact analysis, PRD coverage, activity log | `artifact_graph`, `impact_analysis` |

Goal2story is not part of this UI yet.

## Run

From `IDE3.0/src`, with the dependencies in `requirements.txt` installed:

```sh
uvicorn agentic_flow.api.server:app --reload --port 8000
```

Open http://localhost:8000. Add `?session=<id>` to open a specific session.
Runs use the model configured in `core/models.py` (`.env`): 9 calls per full run.

Sessions are saved as JSON in `IDE3.0/.ide3/sessions/`, which is git-ignored.
Set `IDE3_SESSIONS_DIR` to save them somewhere else.

## Lifecycle

Each extracted item starts as **AI proposed**. You can accept, edit, add or
delete items, or restore a deleted one. The backend keeps the first AI output and
logs every change in the session file; the UI shows the current state only.

A user-added or edited source quote must appear in the PRD word for word.
Deleted IDs are never reused.

When an upstream artifact changes, every stage that depends on it is marked
**out of date**:

| Change | Becomes out of date |
|--------|---------------------|
| SSON or G.1 edited | SSON evaluation, situation & benefits, stakeholders, personas, goals, use cases |
| Situation, problem, benefit, effect, … edited | stakeholders, personas, goals, use cases |
| Stakeholder edited | personas, goals, use cases |
| Persona edited | goals, use cases |
| Goal edited | use cases |

From the out-of-date banner you can **re-run** that stage, **re-run it with
everything downstream**, or **keep it as is**. A re-run replaces that stage's
items. The previous output and its review records are saved in the session's
`snapshots`. The trace graph needs no model, so it is rebuilt after every change.

## Code

- `agentic_flow/api/server.py`: FastAPI routes; also serves this folder.
- `agentic_flow/api/store.py`: sessions, lifecycle, stale rules, background runs.
- `agentic_flow/api/pipeline.py`: composes the existing graphs (full run, one stage per re-run).
- `test/agentic_flow/test_api.py`: backend tests, run on recorded model responses
  from `test/agentic_flow/replay.py` (no model calls).

## Impact analysis

Every manual edit is recorded as a pending change. **Analyze impact**, from the
banner or Trace → Impact, runs `agentic_flow/impact_analysis`:

1. It collects the artifacts linked to each edit (up to two trace steps out,
   plus anything referring to a deleted artifact).
2. One model call assesses each as unaffected, revise or obsolete.
3. Code validates the suggestions.

Each suggestion is one of: revise, remove, remove link, add, or rebuild the use
case model. Accepting one applies it through the same validated edit as a manual
change. Closing a report marks the stages it checked as reviewed.
