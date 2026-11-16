# IDE3.0 source code

A LangGraph chatbot that captures a project's intent step by step: Single Statement of
Need, current situation, expected benefits, then stakeholders.

Run every command below from this `src/` folder.

## 1. Set up

Requires Python 3.11 or newer.

```sh
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Add a model key

The default model is hosted on Groq. Create a free key at https://console.groq.com,
then put it in `agentic_flow/.env` (this file is git-ignored):

```
GROQ_API_KEY=your-key-here
```

To use another provider, set `IDE3_MODEL`; the options are listed in
`agentic_flow/core/models.py`.

## 3. Chat with it

```sh
python -m agentic_flow capture_intent    # SSON, current situation, expected benefits
python -m agentic_flow                   # the whole flow, including stakeholders
```

Type your answer at the `>` prompt. When the bot shows a list with options, reply with
one of them: `yes` confirms, `no` lets you change the list, and `sson` or `problems`
jumps back to that step.

The free Groq tier allows about three model calls a minute. If the bot pauses, it is
waiting on that limit.

## 4. Run the tests

The tests use stand-in models, so they need no key.

```sh
PYTHONPATH=. python ../test/agentic_flow/test_stakeholders.py
```

## 5. Build and draw one graph

Each stage is its own graph with a `build_...()` function that compiles it:

| Graph | Import |
|---|---|
| Capture intent (SSON + context) | `from agentic_flow.capture_intent.graph import build_capture_intent` |
| SSON only | `from agentic_flow.capture_intent.sson.graph import build_capture_sson` |
| Current situation + benefits | `from agentic_flow.capture_intent.context_expected_benefits_current_situation.graph import build_capture_context` |
| Stakeholders | `from agentic_flow.user_modelling.graph import build_user_modelling` |
| Whole flow | `from agentic_flow.graph import build_ide3_chat` |

To compile the capture-intent graph and save its diagram, with subgraphs expanded:

```sh
python -c "
from agentic_flow.capture_intent.graph import build_capture_intent
graph = build_capture_intent()
graph.get_graph(xray=True).draw_mermaid_png(
    output_file_path='agentic_flow/capture_intent/capture_intent_graph.png')
"
```

Drawing sends the node names to the mermaid.ink web service to render the image.

To run a graph on its own in Python, compile it with a checkpointer and resume it with
the user's reply:

```python
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from agentic_flow.capture_intent.graph import build_capture_intent

graph = build_capture_intent(InMemorySaver())
config = {"configurable": {"thread_id": "demo"}}

result = graph.invoke({"project_context": ""}, config)
print(result["__interrupt__"][0].value["prompt_to_user"])

result = graph.invoke(Command(resume="my answer"), config)
```

## Folders

- `agentic_flow/capture_intent/`: SSON, current situation and expected benefits.
- `agentic_flow/user_modelling/`: stakeholders.
- `agentic_flow/core/`: the model setup and shared helpers.
- `agentic_flow/state.py`: everything the chatbot remembers.
