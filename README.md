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

## Run it

The flow takes a PRD and produces the intent (SSON, problems, benefits,
environment), stakeholders, personas, goals, a use case model and a trace graph,
with impact analysis when you edit. See **[`src/README.md`](src/README.md)** for
what each step does, model setup, and how to run the backend and frontend.

Quick start, with Python 3.11+, from this folder:

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r src/requirements.txt
cd src && uvicorn agentic_flow.api.server:app --reload --port 8000
# open http://localhost:8000 and paste src/food_bank_prd.txt
```

Tests need no model: `PYTHONPATH=src python -m unittest discover -s test/agentic_flow`.

Wireframe mock-up:
[prototype](https://raw.githack.com/RishabShine/IDE3.0/main/docs/CDs/Wireframe/prototype/index.html)
(or open `docs/CDs/Wireframe/prototype/index.html` locally).

## Documentation

See `docs/README.md` for the deliverable map. Key PoC-related docs:

- Problem Statement (incl. PoC risks and planned demo):
  `docs/ProblemStatementAndGoals/ProblemStatement.tex`
- Development Plan (original PoC feasibility discussion):
  `docs/DevelopmentPlan/DevelopmentPlan.tex`
- PoC productivity report: `docs/projMngmnt/POC_Productivity_Rep.tex`
- PoC checklist: `docs/Checklists/POC-Checklist.tex`
