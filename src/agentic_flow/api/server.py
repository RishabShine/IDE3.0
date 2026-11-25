"""FastAPI backend for the extension UI (src/extension-UI).

From src/:
    uvicorn agentic_flow.api.server:app --reload --port 8000
then open http://localhost:8000.
"""
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agentic_flow.api import pipeline
from agentic_flow.api.store import COLLECTIONS, SINGLETONS, ApiError, Store
from agentic_flow.core.models import describe_model

UI_DIR = Path(__file__).resolve().parents[2] / "extension-UI"


class NewSession(BaseModel):
    prd: str


class Fields(BaseModel):
    fields: dict[str, Any]


class Accept(BaseModel):
    ids: list[str] | None = None  # None: every proposed item


class Decision(BaseModel):
    decision: str  # accept | reject


class Rerun(BaseModel):
    stage: str
    cascade: bool = False


def create_app(store: Store | None = None) -> FastAPI:
    app = FastAPI(title="IDE3.0 extension UI")
    app.state.store = store or Store()

    def db(request: Request) -> Store:
        return request.app.state.store

    @app.exception_handler(ApiError)
    async def api_error(_request: Request, exc: ApiError):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    @app.get("/api/config")
    def config():
        return {
            "model": describe_model(),
            "stages": [{"id": s, "label": pipeline.STAGE_LABELS[s]} for s in pipeline.STAGES],
            "downstream": pipeline.DOWNSTREAM,
            "collections": {name: {"prefix": c.prefix, "id_key": c.id_key,
                                   "fields": list(c.fields), "stage": c.stage}
                            for name, c in COLLECTIONS.items()},
            "singletons": {name: {"fields": list(f), "stage": st}
                           for name, (f, st) in SINGLETONS.items()},
        }

    @app.get("/api/sessions")
    def sessions(request: Request):
        return db(request).summaries()

    @app.post("/api/sessions")
    def create(body: NewSession, request: Request):
        return db(request).create(body.prd)

    @app.get("/api/sessions/{sid}")
    def get(sid: str, request: Request):
        return db(request).snapshot(sid)

    @app.post("/api/sessions/{sid}/items/{collection}")
    def add(sid: str, collection: str, body: Fields, request: Request):
        return db(request).add_item(sid, collection, body.fields)

    @app.patch("/api/sessions/{sid}/items/{collection}/{item_id}")
    def edit(sid: str, collection: str, item_id: str, body: Fields, request: Request):
        return db(request).edit_item(sid, collection, item_id, body.fields)

    @app.delete("/api/sessions/{sid}/items/{collection}/{item_id}")
    def delete(sid: str, collection: str, item_id: str, request: Request):
        return db(request).delete_item(sid, collection, item_id)

    @app.post("/api/sessions/{sid}/items/{collection}/{item_id}/restore")
    def restore(sid: str, collection: str, item_id: str, request: Request):
        return db(request).restore_item(sid, collection, item_id)

    @app.post("/api/sessions/{sid}/accept/{collection}")
    def accept(sid: str, collection: str, body: Accept, request: Request):
        return db(request).accept(sid, collection, body.ids)

    @app.patch("/api/sessions/{sid}/singletons/{name}")
    def edit_singleton(sid: str, name: str, body: Fields, request: Request):
        return db(request).edit_singleton(sid, name, body.fields)

    @app.post("/api/sessions/{sid}/rerun")
    def rerun(sid: str, body: Rerun, request: Request):
        return db(request).rerun(sid, body.stage, body.cascade)

    @app.post("/api/sessions/{sid}/stages/{stage}/keep")
    def keep(sid: str, stage: str, request: Request):
        return db(request).dismiss_stale(sid, stage)

    @app.post("/api/sessions/{sid}/impact")
    def analyze_impact(sid: str, request: Request):
        return db(request).analyze_impact(sid)

    @app.post("/api/sessions/{sid}/impact/{report_id}/proposals/{proposal_id}")
    def decide(sid: str, report_id: str, proposal_id: str, body: Decision, request: Request):
        return db(request).decide_proposal(sid, report_id, proposal_id, body.decision)

    @app.post("/api/sessions/{sid}/impact/{report_id}/close")
    def close_report(sid: str, report_id: str, request: Request):
        return db(request).close_report(sid, report_id)

    @app.get("/")
    def index():
        return FileResponse(UI_DIR / "index.html")

    app.mount("/", StaticFiles(directory=UI_DIR), name="ui")
    return app


app = create_app()
