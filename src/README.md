# IDE3.0 source code

The IDE3.0 agentic requirements flow (LangGraph) and a browser UI for it. You give
it a PRD. It extracts the intent, models the users, extracts goals, and builds a
rough use case model. Every artifact is traced back to the PRD and to the others.

## The flow

`build_ide3_chat()` in `agentic_flow/graph.py` starts from `{"prd": "..."}` and
asks no questions. The diagram is
[`agentic_flow/requirement_engineer_graph.png`](agentic_flow/requirement_engineer_graph.png).

| # | Step | What it does | Writes | Model calls |
|---|------|--------------|--------|-------------|
| 1 | **Capture intent: SSON** (`capture_intent/sson`) | Finds the single statement of need (SSON), or writes one and marks it 🚩, plus what/how/why/success and the G.1 context. A second call scores the SSON on five L04 criteria. The score is reported but doesn't block the flow. | `captured_intent` | 2 |
| 2 | **Capture intent: context** (`capture_intent/context_…`) | Extracts the G.2 current situation and problems, the G.3 benefits (each linked to problems, with a measure when the PRD gives one), and the E.5 effects, E.6 invariants, constraints and scope exclusions. Every item keeps its PRD quote; anything the PRD doesn't say is marked 🚩. | `captured_intent` | 3 |
| 3 | **User modelling** (`user_modelling`) | Extracts stakeholders (direct or indirect), then personas (MSF template), each linked to its stakeholder. | `stakeholder_metadata`, `persona_metadata` | 2 |
| 4 | **Goals** (`goals`) | Extracts hard and soft goals (L07/L08). Each goal has actors linked to stakeholders, resources, plans, a justification, the benefits it delivers and its PRD quote. | `goal_metadata` | 1 |
| 5 | **Use case model** (`use_cases`) | Builds a rough L13 use case model: actors (human, system or organization), use cases named with a verb (each with a primary actor, supporting actors and the goals it achieves) and «include»/«extend» links. Code resolves every reference and runs L13 pitfall checks such as include chains, unused actors and uncovered goals. | `use_case_metadata` | 1 |
| 6 | **Artifact graph** (`artifact_graph`) | No model. Turns every artifact into a node and every stored ID reference into a trace link, then reports gaps: missing types, dangling links, and unaddressed or uncovered items. | `artifact_graph` | 0 |

A full run makes 9 model calls. Code assigns every ID (`Problem-1`, `Goal-2`,
`UC-3`, …) and checks every link; the model never chooses IDs.

**Impact analysis** (`impact_analysis`) runs on demand after you edit
artifacts in the UI:

1. It follows the trace links up to two steps out from each edit, plus anything
   that refers to a deleted artifact.
2. One model call decides, for each linked artifact, whether it is unaffected,
   needs revising or is obsolete, and proposes the edits.
3. Code validates every suggestion.

You accept or reject each suggestion; nothing changes on its own.

**Goal2Story** (`goal2story`) writes user stories per goal. It is not in the main
flow but still runs on its own after the goals stage.

## Setup

From the repository root (`IDE3.0/`), with Python 3.11+:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt
```

Pick a model in a `.env` file at the repository root. The first match wins
(see `agentic_flow/core/models.py`):

| Set | Uses |
|-----|------|
| `TOKENROUTER_API_KEY` (+ optional `TOKENROUTER_MODEL`) | TokenRouter, default `openai/gpt-5.4-nano` |
| `OLLAMA_API_KEY` (+ optional `OLLAMA_MODEL`) | Ollama Cloud, default `gpt-oss:120b` |
| neither | local [Ollama](https://ollama.com), default `qwen2.5:7b` (`ollama pull qwen2.5:7b`) |

`IDE3_PROVIDER` forces a provider, and `IDE3_MODEL` overrides the model name.

## Real model calls

Everything below calls the model chosen in `.env` (see Setup): the main
graph, every subgraph, the backend and the UI. Each model reply is printed as it
arrives; add `--quiet` to hide them. Only the automated tests use recorded
answers, and they block the network so they can never reach a model.

## Run the main graph in the terminal

The main graph's first input is the PRD. Run it from `src/`:

```sh
python -m agentic_flow.graph                                  # asks you to paste the PRD first
python -m agentic_flow.graph --prd food_bank_prd.txt --out run.json
```

Without `--prd` it prints `Paste your PRD. The flow starts from it.` Paste the
whole document, then press Enter on two empty lines, or type `END`. It then
runs every step (intent, user modelling, goals, use cases, trace). It prints a
`✓` line as each node finishes, then a summary of every artifact and trace gap.
`--out run.json` saves the final state so the subgraphs below can start from it.

## Run each subgraph

`python -m agentic_flow.run <graph>`, from `src/`. Given a PRD, it first runs
any earlier steps the graph needs. With `--state run.json --only`, it runs just
that graph on a state saved by `--out`. `python -m agentic_flow.run --help`
lists every option.

| Graph | What it does | From the PRD | From a saved run, this graph only |
|-------|--------------|--------------|-----------------------------------|
| `sson` | SSON and G.1, then the L04 evaluation | `python -m agentic_flow.run sson --prd food_bank_prd.txt` | `python -m agentic_flow.run sson --state run.json --only` |
| `context` | G.2 problems, G.3 benefits, E.5/E.6 environment | `python -m agentic_flow.run context --prd food_bank_prd.txt` | `python -m agentic_flow.run context --state run.json --only` |
| `capture_intent` | `sson`, then `context` | `python -m agentic_flow.run capture_intent --prd food_bank_prd.txt` | `python -m agentic_flow.run capture_intent --state run.json --only` |
| `stakeholders` | Stakeholders from the PRD and intent | `python -m agentic_flow.run stakeholders --prd food_bank_prd.txt` | `python -m agentic_flow.run stakeholders --state run.json --only` |
| `personas` | Personas linked to stakeholders | `python -m agentic_flow.run personas --prd food_bank_prd.txt` | `python -m agentic_flow.run personas --state run.json --only` |
| `user_modelling` | `stakeholders`, then `personas` | `python -m agentic_flow.run user_modelling --prd food_bank_prd.txt` | `python -m agentic_flow.run user_modelling --state run.json --only` |
| `goals` | Hard and soft goals linked to benefits and stakeholders | `python -m agentic_flow.run goals --prd food_bank_prd.txt` | `python -m agentic_flow.run goals --state run.json --only` |
| `use_cases` | Rough L13 use case model | `python -m agentic_flow.run use_cases --prd food_bank_prd.txt` | `python -m agentic_flow.run use_cases --state run.json --only` |
| `artifact_graph` | Trace links and gaps (no model call) | `python -m agentic_flow.run artifact_graph --prd food_bank_prd.txt` | `python -m agentic_flow.run artifact_graph --state run.json --only` |
| `impact` | Impact analysis of one edit or delete | `python -m agentic_flow.run impact --state run.json --edit problems:Problem-2 "description=About 20 kg of produce is thrown out every week."` | `python -m agentic_flow.run impact --state run.json --delete benefits:Benefit-1` |
| `goal2story` | User stories per goal (outside the main flow) | `python -m agentic_flow.run goal2story --prd food_bank_prd.txt` | `python -m agentic_flow.run goal2story --state run.json --only` |

To chain steps yourself, save each one with `--out` and pass it to the next
with `--state`:

```sh
python -m agentic_flow.run capture_intent --prd food_bank_prd.txt --out step1.json
python -m agentic_flow.run user_modelling --state step1.json --only --out step2.json
python -m agentic_flow.run goals --state step2.json --only --out step3.json
```

## Run the backend and the UI

One command starts both. The FastAPI backend (`agentic_flow/api/`) serves the
UI (`extension-UI/`, plain HTML/CSS/JS with no build step). From `src/`:

```sh
uvicorn agentic_flow.api.server:app --reload --port 8000
```

Open http://localhost:8000, paste a PRD (try `food_bank_prd.txt`) on the
Welcome page, and click **Run the flow**:

- **Seven pages** fill in as each step finishes: Welcome, Capture intent,
  Situation & benefits, Stakeholders, Personas, Goals, Use cases.
- **Editing:** accept, edit, add, delete or restore items. Edits mark later
  steps as out of date, and the banner offers a re-run.
- **Trace page:** the graph with its legend, **Impact** (analyze your edits and
  accept or reject the suggestions), PRD coverage, and the activity log.

Sessions are saved in `IDE3.0/.ide3/sessions/` (git-ignored). Add
`?session=<id>` to the URL to reopen one. More detail:
[`extension-UI/README.md`](extension-UI/README.md).

## Tests

The tests need no model: model calls are stubbed or replayed from recorded answers
(`test/agentic_flow/replay.py`), and the network is blocked while they run. From the
repository root:

```sh
PYTHONPATH=src python -m unittest discover -s test/agentic_flow
```

## Layout

| Path | Role |
|------|------|
| `agentic_flow/graph.py` | The main flow (`python -m agentic_flow.graph`) |
| `agentic_flow/run.py` | Terminal runner for the main graph and every subgraph |
| `agentic_flow/capture_intent/` | SSON, G.1–G.3, E.5/E.6 from the PRD |
| `agentic_flow/user_modelling/` | Stakeholders and personas |
| `agentic_flow/goals/` | Hard/soft goals with actors, linked to benefits and stakeholders |
| `agentic_flow/use_cases/` | Rough use case model (3RA3 L13) with code checks |
| `agentic_flow/artifact_graph/` | Links every artifact into one trace graph and finds gaps |
| `agentic_flow/impact_analysis/` | Impact analysis agent for edits |
| `agentic_flow/goal2story/` | User stories per goal (outside the main flow) |
| `agentic_flow/api/` | FastAPI backend: sessions, review state, re-runs, impact analysis |
| `agentic_flow/core/` | Model configuration and shared nodes |
| `agentic_flow/draw_graphs.py` | Redraws every graph diagram with subgraphs expanded |
| `extension-UI/` | Browser UI served by the backend |
| `food_bank_prd.txt` | Sample PRD |
