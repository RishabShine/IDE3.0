# IDE3.0 source code

Python implementation of the IDE3.0 agentic requirements workflow.

## Layout

| Path | Role |
|------|------|
| `agentic_flow/` | LangGraph pipeline (outer graph + subgraphs) |
| `agentic_flow/prd_intake/` | Collect raw PRD / product context text |
| `agentic_flow/capture_intent/` | Single Statement of Need capture + evaluation |
| `agentic_flow/user_modelling/` | Stakeholders and personas |
| `agentic_flow/goal2story/` | Goal → actors → impacts → deliverables → stories |
| `agentic_flow/core/` | Shared model helpers and nodes |
| `requirements.txt` | Python dependencies |
| `TraceToDesign.md` | Placeholder for code ↔ design module mapping |

## Setup

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt
```

Requires **Python 3.11+** and a running **Ollama** instance for live demos
(default model `llama2:7b-chat`, overridable with `IDE3_MODEL`).

## Run the PoC demo

```sh
cd src
python -m agentic_flow.goal2story.demo --n 1
python -m agentic_flow.goal2story.demo --full --n 1
```

See `agentic_flow/goal2story/README.md` and
`agentic_flow/user_modelling/README.md` for subgraph details.
