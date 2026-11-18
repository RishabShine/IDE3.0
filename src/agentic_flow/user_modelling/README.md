# User modelling

The user-modelling graph runs stakeholders, then personas, then END. Each stage
is a separate subgraph and evaluates only the records the engineer provides.
The engineer can add, edit, or remove drafts before confirming each stage.
The outer IDE3.0 graph runs SSON capture before user modelling. The Goal2Story
handoff can be added later.

The flow is:

```text
starter → process response → evaluate
                                  ↑               |
                                  |       needs refinement
                                  |               ↓
                                  └──── refinement input

evaluate → all checks met → confirmation
                                                    |
                              changes/questions ────┘ → process response
                                                    |
                                                 APPROVE
                                                    ↓
                                                 finalize → END
```

Each refinement turn uses two model calls: one interprets the user's response
into requested draft additions, edits, and removals; the other evaluates the
updated drafts. Under `stakeholder_metadata` or `persona_metadata`, each stage
retains the reusable project context message, current drafts, the last prompt shown to the
user, their latest reply, and the most recent completed evaluation. There is no growing
message history. Each model call receives task-specific instructions, the
reusable context, and one current-state request containing that latest exchange.
The single evaluation record is replaced after each successful evaluation.
Its draft-version marker prevents old verdicts from approving edited drafts.
Evaluation does not approve the draft list.

Both starter nodes use `AgentState["captured_intent"]` when it is supplied,
falling back to an empty context when upstream intent is not available. The
persona starter also includes finalized stakeholders. No sample project is
hardcoded and no separate raw intent copy is stored in stage metadata.
The starter node prepares this context and displays the initial guidance in one
step, without reading files or calling the model. It commits the prepared state
when the user replies. On interrupt resume, preparing the context again is safe
and does not append duplicate messages. The evaluation is initially
empty, and the starter guidance is retained as the first prompt shown.

With `src` on the Python import path and Ollama running the configured model:

```python
from langgraph.types import Command
from agentic_flow.user_modelling.graph import user_modelling_graph

config = {"configurable": {"thread_id": "project-1-stakeholders"}}
result = user_modelling_graph.invoke(
    {"captured_intent": captured_intent}, config
)

# The UI displays result["__interrupt__"][0].value["prompt_to_user"].
# Resume the same graph and thread with the user's text, repeating as needed.
result = user_modelling_graph.invoke(Command(resume=user_reply), config)
```

The default `InMemorySaver` checkpoints current drafts and the latest exchange while the
process runs when using the exported standalone graph. The outer graph also
uses an in-memory checkpointer, inherited by both subgraphs. The builder
`build_user_modelling(checkpointer=...)` accepts another checkpointer when
durable storage is decided; leaving it unset enables parent inheritance.
Keep the same `thread_id` when resuming. A process restart loses the default
in-memory checkpoints.

Finalized records are available at
`result["stakeholder_metadata"]["finalized_stakeholders"]`. Their draft IDs are
strings such as `Stakeholder-1`, preserved across edits. `next_draft_number` is
only the internal numeric counter for assigning new IDs. Assigning persistent
artifact IDs and saving to the project remain to be
connected.

## Model validation and recovery

Structured responses reject unexpected fields. Before applying any operations,
the nodes validate references, repeated/conflicting operations, duplicate names,
and attempts to remove and recreate the same record. Duplicate comparisons
ignore case, whitespace, and trailing involvement labels. This catches exact
label variants; semantic overlap between differently named groups still needs
evaluation and user review. New IDs are application-assigned; an ID supplied
by the model on the very first submission is treated as a new-record proposal.

A malformed response or invalid set of references gets one corrective call.
If it remains invalid, processing returns to refinement with the drafts and ID
counter unchanged. Model connection failures also return to refinement. The
engineer can rephrase the reply without losing the thread's records.

An evaluation must cover every current draft exactly once and use valid
related IDs. If evaluation fails, the edited drafts remain available, but the
old evaluation is not treated as a current pass. Enter RETRY at the refinement
prompt to evaluate the current records again without interpreting another edit,
or describe further changes. `model_error` in stage metadata records the
failed stage and diagnostic detail. Approval is disabled until the error is
resolved and a successful evaluation covers the current draft version.

These safeguards validate structure and references; they cannot prove that a
model faithfully interpreted arbitrary natural-language input. The prompts
require preserving explicit user facts, distinguish questions from changes,
and keep project examples separate from confirmed intent. Live model tests
are still needed to assess those behaviours.

Run the graph tests from the repository root with dependencies installed:

```sh
PYTHONPATH=src python -m unittest discover -s test/agentic_flow -v
```

The tests use controlled model responses, exercising real graph transitions,
interrupts, and checkpoints without contacting Ollama.

## Generate a graph image

Use LangGraph's built-in drawing method, matching the capture-intent graph.
From the `src` directory, run this with the project dependencies installed:

```python
from agentic_flow.user_modelling.graph import user_modelling_graph

user_modelling_graph.get_graph(xray=True).draw_mermaid_png(
    output_file_path="agentic_flow/user_modelling/user_modelling_graph.png"
)
```

The same optional call is commented at the bottom of the graph file. With its
usual defaults, this renderer uses the external Mermaid rendering service.
