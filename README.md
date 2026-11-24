# IDE3.0

**Team 8** — Qusay Qadir, Rishab Shine, Tyler Yue, Vedant Patel, Saumy Patel

Capstone project (SFWRENG 4G06): tool support for AI-native software
engineering. IDE3.0 helps engineers capture engineering intent, derive
stakeholders / personas / user stories, and (later) keep that intent linked to
design, code, and verification inside an IDE workflow.

- **Repository:** https://github.com/RishabShine/IDE3.0
- **Project pages / PDFs:** https://RishabShine.github.io/IDE3.0/
- **Supervisor:** Dr. Istvan David
- **TA:** Lucas Dutton

## Repository layout

| Path | Contents |
|------|----------|
| `docs/` | Course deliverables (Problem Statement, Dev Plan, SRS, HA, VnV, design, CDs, productivity reports) |
| `pdfs/` | Generated PDFs mirrored from documentation builds |
| `src/` | Source code — primarily the `agentic_flow` LangGraph pipeline |
| `test/` | Automated tests for the agentic flow |
| `refs/` | BibTeX and reference material |
| `.github/workflows/` | CI (LaTeX/PDF build and pages deploy) |

## Proof of Concept (live demo)

The PoC shows the intent-capture foundation, not full code traceability yet.

1. Install dependencies (Python 3.11+):

   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r src/requirements.txt
   ```

2. Install and run [Ollama](https://ollama.com), then pull a model:

   ```sh
   ollama pull llama2:7b-chat
   # optional: IDE3_MODEL=qwen2.5:7b
   ```

3. From `src/`:

   ```sh
   cd src
   python -m agentic_flow.goal2story.demo --n 1      # short Goal2Story demo
   python -m agentic_flow.goal2story.demo --full --n 1  # full pipeline
   ```

4. Tests (no Ollama required), from the repo root:

   ```sh
   PYTHONPATH=src python -m unittest discover -s test/agentic_flow -v
   ```

5. Wireframe UI mock-up:
   [prototype](https://raw.githack.com/RishabShine/IDE3.0/main/docs/CDs/Wireframe/prototype/index.html)
   or open `docs/CDs/Wireframe/prototype/index.html` locally.

## Documentation

See `docs/README.md` for the deliverable map. Key PoC-related docs:

- Problem Statement (incl. PoC risks and planned demo):
  `docs/ProblemStatementAndGoals/ProblemStatement.tex`
- Development Plan (original PoC feasibility discussion):
  `docs/DevelopmentPlan/DevelopmentPlan.tex`
- PoC productivity report: `docs/projMngmnt/POC_Productivity_Rep.tex`
- PoC checklist: `docs/Checklists/POC-Checklist.tex`
