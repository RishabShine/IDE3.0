# D0 — Proof of Concept Demonstration

This folder is for PoC demo materials. The live demo is the agentic workflow in
the repository, not a slide deck (the PoC checklist asks for **no slides**).

## What we demonstrate

1. **Live code** (preferred): from `src/`, with a model configured (local
   Ollama `qwen2.5:7b` by default, or keys in the repo-root `.env`):

   ```sh
   python -m agentic_flow.graph --prd food_bank_prd.txt --out run.json
   ```

   Optional UI (same pipeline):

   ```sh
   uvicorn agentic_flow.api.server:app --reload --port 8000
   # open http://localhost:8000
   ```

2. **Fallback**: saved `run.json` / printed artifact-graph summary, unit tests
   under `test/agentic_flow/`, and/or the Wireframe prototype at
   `docs/CDs/Wireframe/prototype/index.html`.

3. **Risks and plan**: documented in
   `docs/ProblemStatementAndGoals/ProblemStatement.tex` (Proof of Concept
   section) and summarized in `docs/projMngmnt/POC_Productivity_Rep.tex`.

## Checklist

See `docs/Checklists/POC-Checklist.tex` /
`pdfs/Checklists/POC-Checklist.pdf`.
