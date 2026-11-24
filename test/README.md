# IDE3.0 tests

Automated tests for the agentic requirements workflow.

## Layout

| Path | Role |
|------|------|
| `agentic_flow/` | Unit tests for stakeholders, personas, and Goal2Story graphs |
| `local_testing/` | Local seed data / manual exploration helpers |

The graph tests use stubbed model responses so they exercise real LangGraph
transitions, interrupts, and checkpoints **without** contacting Ollama.

## Run

From the repository root (dependencies from `src/requirements.txt` installed):

```sh
PYTHONPATH=src python -m unittest discover -s test/agentic_flow -v
```
