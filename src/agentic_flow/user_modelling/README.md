# User modelling

The current graph implements stakeholder identification. The outer IDE3.0 graph
now runs SSON capture, then this graph, then END. It can also run independently
for testing. Personas and the Goal2Story handoff can be added later.

The flow is:

```text
starter → process response → evaluate
                                  ↑               |
                                  |       needs refinement
                                  |               ↓
                                  └──── refinement input

evaluate → all checks met, no pending suggestions → confirmation
                                                    |
                              changes/questions ────┘ → process response
                                                    |
                                                 APPROVE
                                                    ↓
                                                 finalize → END
```

Each refinement turn uses two model calls: one interprets the user's response
into draft changes and suggestion decisions; the other evaluates the updated
drafts. Under `stakeholder_metadata`, the graph retains the reusable project
context message, current drafts and decisions, the last prompt shown to the
user, their latest reply, and the most recent completed evaluation. There is no growing
message history. Each model call receives task-specific instructions, the
reusable context, and one current-state request containing that latest exchange.
The single evaluation record is replaced after each successful evaluation.
Its draft-version marker prevents old verdicts from approving edited drafts.
Evaluation does not approve the draft list.

Upstream intent integration is pending. The starter currently uses an empty
context placeholder marked `REPLACE WITH ACTUAL INTENT DATA WHEN MERGED`.
Once merged, select the needed intent fields directly from `AgentState` to
prepare the context message. No separate raw intent copy is kept in stakeholder
metadata. The `captured_intent` input below is reserved for that integration.
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
`result["stakeholder_metadata"]["finalized_stakeholders"]`. Their IDs are draft
IDs; assigning persistent artifact IDs and saving to the project remain to be
connected. Schema or model errors raise an exception instead of approving or
finalizing an invalid result; the last completed graph state is checkpointed.

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
