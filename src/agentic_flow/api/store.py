"""Sessions: one PRD, the pipeline's output for it, and every change made since.

`session["state"]` is the AgentState the graphs read and write. Review data
(lifecycle status, original AI text, change history, deleted items) lives
beside it in `session["items"]` and `session["deleted"]`, so it never reaches
a prompt. Sessions are saved as JSON under IDE3_SESSIONS_DIR
(default: IDE3.0/.ide3/sessions).
"""
import copy
import json
import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic_flow.api import pipeline
from agentic_flow.artifact_graph.node import build_artifact_graph
from agentic_flow.capture_intent.common import traced

SESSIONS_DIR = Path(os.environ.get("IDE3_SESSIONS_DIR")
                    or Path(__file__).resolve().parents[3] / ".ide3" / "sessions")
MAX_EVENTS = 1000


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class Collection:
    parent: str     # state key holding the list's container
    key: str        # list key inside it
    prefix: str     # ID prefix, e.g. Problem -> Problem-5
    id_key: str
    fields: tuple[str, ...]  # what the user may set
    stage: str      # the stage that produces it


_SOURCED = ("description", "source")
COLLECTIONS: dict[str, Collection] = {
    "problems": Collection("captured_intent", "problems", "Problem", "id", _SOURCED, "context"),
    "benefits": Collection("captured_intent", "benefits", "Benefit", "id",
                           _SOURCED + ("addresses", "measure"), "context"),
    "effects": Collection("captured_intent", "effects", "Effect", "id", _SOURCED, "context"),
    "invariants": Collection("captured_intent", "invariants", "Invariant", "id", _SOURCED, "context"),
    "constraints": Collection("captured_intent", "constraints", "Constraint", "id", _SOURCED, "context"),
    "scope_exclusions": Collection("captured_intent", "scope_exclusions", "Exclusion", "id",
                                   _SOURCED, "context"),
    "stakeholders": Collection("stakeholder_metadata", "stakeholders", "Stakeholder",
                               "stakeholder_id",
                               ("name", "involvement", "summary", "justification"),
                               "stakeholders"),
    "personas": Collection("persona_metadata", "personas", "Persona", "persona_id",
                           ("stakeholder_id", "name", "role", "status_and_trust_level",
                            "demographics", "ksa", "gmc", "usage_patterns"),
                           "personas"),
    "goals": Collection("goal_metadata", "goals", "Goal", "goal_id",
                        ("statement", "source", "goal_type", "benefit_ids", "actors",
                         "resources", "plans", "justification"),
                        "goals"),
}

# Single records inside captured_intent, edited as a whole.
SINGLETONS: dict[str, tuple[tuple[str, ...], str]] = {
    "sson": (("single_statement_intent", "what", "how", "why", "success_measure",
              "context_and_objective"), "sson"),
    "situation": (("current_situation",), "context"),
}
_OPTIONAL_TEXT = {"what", "how", "why", "success_measure", "source", "measure"}
_REQUIRED_TEXT = {"description", "statement"}  # whichever a collection has
_ACTOR_FIELDS = ("name", "stakeholder_id", "role", "involvement")

# What each stage produces, for lifecycle tracking.
STAGE_RECORDS = {
    "sson": ["singleton:sson"],
    "sson_eval": [],
    "context": ["singleton:situation", *[c for c, v in COLLECTIONS.items() if v.stage == "context"]],
    "stakeholders": ["stakeholders"],
    "personas": ["personas"],
    "goals": ["goals"],
    "use_cases": [],  # shown, not yet edited item by item
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


class Store:
    def __init__(self, directory: Path = SESSIONS_DIR):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()       # guards session dicts
        self.run_lock = threading.Lock()    # one pipeline run at a time
        self.sessions: dict[str, dict] = {}
        for path in sorted(self.dir.glob("*.json")):
            try:
                session = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if session.get("running"):  # the server stopped mid-run
                session["running"] = False
                for stage in session["stages"].values():
                    if stage["status"] in ("running", "queued"):
                        stage.update(status="error", error="The server stopped during the run.")
            self._upgrade(session)
            self.sessions[session["id"]] = session

    @staticmethod
    def _upgrade(session: dict) -> None:
        """Sessions saved before a stage or feature existed get its empty form."""
        session.setdefault("changes", [])
        session.setdefault("impact_reports", [])
        for name in pipeline.STAGES:
            session["stages"].setdefault(name, {
                "status": "pending", "label": pipeline.STAGE_LABELS[name], "started_at": None,
                "finished_at": None, "error": None, "stale_reason": None})

    # Reading ------------------------------------------------------------------

    def _get(self, sid: str) -> dict:
        try:
            return self.sessions[sid]
        except KeyError:
            raise ApiError(404, f"No session {sid}.") from None

    def snapshot(self, sid: str) -> dict:
        with self.lock:
            return copy.deepcopy(self._get(sid))

    def summaries(self) -> list[dict]:
        with self.lock:
            rows = []
            for s in self.sessions.values():
                first_line = next((l.strip() for l in s["state"].get("prd", "").splitlines()
                                   if l.strip()), "Untitled PRD")
                rows.append({"id": s["id"], "title": first_line[:80],
                             "created_at": s["created_at"], "updated_at": s["updated_at"],
                             "running": s["running"]})
            return sorted(rows, key=lambda r: r["updated_at"], reverse=True)

    # Persistence and bookkeeping ----------------------------------------------

    def _save(self, s: dict) -> None:
        s["updated_at"] = now()
        path = self.dir / f"{s['id']}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)

    def _event(self, s: dict, kind: str, detail: str, **extra) -> None:
        s["events"].append({"at": now(), "kind": kind, "detail": detail, **extra})
        del s["events"][:-MAX_EVENTS]

    def _refresh_trace(self, s: dict) -> None:
        s["state"]["artifact_graph"] = build_artifact_graph(s["state"])
        s["stages"]["trace"].update(status="done", finished_at=now(), error=None)

    def _mark_stale(self, s: dict, stages: list[str], reason: str) -> None:
        for name in stages:
            stage = s["stages"][name]
            if stage["status"] in ("done", "stale"):
                stage.update(status="stale", stale_reason=reason)
        if stages:
            self._event(s, "stale", reason, stages=stages)

    def _require_idle(self, s: dict) -> None:
        if s["running"]:
            raise ApiError(409, "The pipeline is still running; wait for it to finish.")

    # Lifecycle records ----------------------------------------------------------

    def _records(self, s: dict, name: str) -> list[tuple[str, dict]]:
        """(meta key, current value) for every record a collection or singleton holds."""
        if name.startswith("singleton:"):
            single = name.split(":", 1)[1]
            fields, _ = SINGLETONS[single]
            intent = s["state"].get("captured_intent") or {}
            if not any(intent.get(f) for f in fields):
                return []
            return [(name, {f: intent.get(f) for f in fields})]
        coll = COLLECTIONS[name]
        return [(f"{name}:{item[coll.id_key]}", item) for item in self._list(s, name)]

    def _register(self, s: dict, stage: str) -> None:
        """Start a lifecycle record for each item a stage produced."""
        for name in STAGE_RECORDS.get(stage, []):
            for key, value in self._records(s, name):
                if key not in s["items"]:
                    s["items"][key] = {
                        "status": "proposed", "origin": "ai", "original": copy.deepcopy(value),
                        "history": [{"at": now(), "action": "extracted", "by": "ai",
                                     "after": copy.deepcopy(value)}],
                    }

    def _reset(self, s: dict, stage: str, reason: str) -> None:
        """Before a re-run replaces a stage's output: keep the old output, drop its records."""
        names = STAGE_RECORDS.get(stage, [])
        saved = {}
        for name in names:
            if name.startswith("singleton:"):
                saved[name] = dict(self._records(s, name)).get(name)
            else:
                saved[name] = copy.deepcopy(self._list(s, name))
                s["deleted"].pop(name, None)
            for key in [k for k in s["items"] if k == name or k.startswith(f"{name}:")]:
                saved.setdefault("_items", {})[key] = s["items"].pop(key)
        if names:
            s["snapshots"].append({"at": now(), "stage": stage, "reason": reason, "data": saved})

    def _list(self, s: dict, collection: str) -> list[dict]:
        coll = COLLECTIONS[collection]
        parent = s["state"].setdefault(coll.parent, {})
        return parent.setdefault(coll.key, [])

    def _find(self, s: dict, collection: str, item_id: str) -> tuple[Collection, list, int]:
        if collection not in COLLECTIONS:
            raise ApiError(404, f"Unknown collection {collection}.")
        coll = COLLECTIONS[collection]
        items = self._list(s, collection)
        for index, item in enumerate(items):
            if item[coll.id_key] == item_id:
                return coll, items, index
        raise ApiError(404, f"No {item_id} in {collection}.")

    def _next_id(self, s: dict, collection: str) -> str:
        coll = COLLECTIONS[collection]
        used = [item[coll.id_key] for item in self._list(s, collection)]
        used += [d["item"][coll.id_key] for d in s["deleted"].get(collection, [])]
        used += [k.split(":", 1)[1] for k in s["items"] if k.startswith(f"{collection}:")]
        numbers = [int(m.group(1)) for u in used if (m := re.fullmatch(rf"{coll.prefix}-(\d+)", u))]
        return f"{coll.prefix}-{max(numbers, default=0) + 1}"

    def _clean(self, s: dict, collection: str, fields: dict, current: dict) -> dict:
        coll = COLLECTIONS[collection]
        unknown = set(fields) - set(coll.fields)
        if unknown:
            raise ApiError(422, f"{collection} has no field(s) {', '.join(sorted(unknown))}.")
        prd = s["state"].get("prd", "")
        clean: dict[str, Any] = {}
        for field, value in fields.items():
            if field in ("addresses", "benefit_ids"):
                target = "problems" if field == "addresses" else "benefits"
                known = {x["id"] for x in self._list(s, target)}
                ids = list(dict.fromkeys(_text(v) for v in (value or []) if _text(v)))
                bad = [i for i in ids if i not in known]
                if bad:
                    raise ApiError(422, f"Unknown {target[:-1]}(s): {', '.join(bad)}.")
                clean[field] = ids
            elif field == "goal_type":
                value = _text(value) or None
                if value not in (None, "hard", "soft"):
                    raise ApiError(422, "Goal type must be hard, soft or empty.")
                clean[field] = value
            elif field == "resources":
                items = value.splitlines() if isinstance(value, str) else (value or [])
                clean[field] = list(dict.fromkeys(t for t in (_text(v) for v in items) if t))
            elif field == "actors":
                clean[field] = self._clean_actors(s, value)
            elif field == "involvement":
                value = _text(value) or None
                if value not in (None, "direct", "indirect"):
                    raise ApiError(422, "Involvement must be direct, indirect or empty.")
                clean[field] = value
            elif field == "stakeholder_id":
                value = _text(value) or None
                known = {x["stakeholder_id"] for x in self._list(s, "stakeholders")}
                if value is not None and value not in known:
                    raise ApiError(422, f"No stakeholder {value}.")
                clean[field] = value
            elif field == "source":
                value = str(value or "").strip() or None
                if value is not None and not traced(value, prd):
                    raise ApiError(422, "That source quote is not in the PRD word for word. "
                                        "Paste the exact PRD text, or leave it empty.")
                clean[field] = value
            else:
                value = _text(value)
                clean[field] = (value or None) if field in _OPTIONAL_TEXT else value
        merged = {**current, **clean}
        for required in _REQUIRED_TEXT & set(coll.fields):
            if not _text(merged.get(required)):
                raise ApiError(422, f"A {required} is required.")
        if collection == "stakeholders" and not merged.get("name"):
            raise ApiError(422, "A stakeholder needs a name.")
        if collection == "personas" and not (merged.get("name") or merged.get("role")):
            raise ApiError(422, "A persona needs a name or a role.")
        if collection == "benefits":
            clean["kind"] = "hard" if merged.get("measure") else "soft"
        return clean

    def _clean_actors(self, s: dict, actors: Any) -> list[dict]:
        if not isinstance(actors, list):
            raise ApiError(422, "Actors must be a list.")
        known = {x["stakeholder_id"] for x in self._list(s, "stakeholders")}
        clean = []
        for actor in actors:
            if not isinstance(actor, dict):
                raise ApiError(422, "Each actor must be an object.")
            row = {f: _text(actor.get(f)) for f in _ACTOR_FIELDS}
            if not any(row.values()):
                continue  # an empty row in the form
            if not row["name"]:
                raise ApiError(422, "Each actor needs a name.")
            row["stakeholder_id"] = row["stakeholder_id"] or None
            if row["stakeholder_id"] is not None and row["stakeholder_id"] not in known:
                raise ApiError(422, f"No stakeholder {row['stakeholder_id']}.")
            clean.append(row)
        return clean

    def _after_change(self, s: dict, stage: str, reason: str) -> None:
        self._mark_stale(s, pipeline.DOWNSTREAM.get(stage, []), reason)
        self._refresh_trace(s)
        self._save(s)

    # Item actions -----------------------------------------------------------------

    def add_item(self, sid: str, collection: str, fields: dict) -> dict:
        with self.lock:
            s = self._get(sid)
            self._require_idle(s)
            if collection not in COLLECTIONS:
                raise ApiError(404, f"Unknown collection {collection}.")
            coll = COLLECTIONS[collection]
            item_id = self._next_id(s, collection)
            blank = {f: ("" if f not in _OPTIONAL_TEXT | {"involvement", "stakeholder_id",
                                                           "goal_type"} else None)
                     for f in coll.fields}
            for list_field in ("addresses", "benefit_ids", "actors", "resources"):
                if list_field in coll.fields:
                    blank[list_field] = []
            item = {coll.id_key: item_id, **blank}
            item.update(self._clean(s, collection, fields, item))
            self._list(s, collection).append(item)
            s["items"][f"{collection}:{item_id}"] = {
                "status": "added", "origin": "user", "original": None,
                "history": [{"at": now(), "action": "added", "by": "user",
                             "after": copy.deepcopy(item)}],
            }
            self._record_change(s, f"{collection}:{item_id}", "added", None, item)
            self._event(s, "edit", f"Added {item_id}", ref=f"{collection}:{item_id}")
            self._after_change(s, coll.stage, f"{item_id} was added")
            return copy.deepcopy(s)

    def edit_item(self, sid: str, collection: str, item_id: str, fields: dict) -> dict:
        with self.lock:
            s = self._get(sid)
            self._require_idle(s)
            coll, items, index = self._find(s, collection, item_id)
            before = copy.deepcopy(items[index])
            items[index].update(self._clean(s, collection, fields, items[index]))
            after = copy.deepcopy(items[index])
            if after == before:
                return copy.deepcopy(s)
            meta = s["items"][f"{collection}:{item_id}"]
            meta["status"] = "edited"
            meta["history"].append({"at": now(), "action": "edited", "by": "user",
                                    "before": before, "after": after})
            self._record_change(s, f"{collection}:{item_id}", "edited", before, after)
            self._event(s, "edit", f"Edited {item_id}", ref=f"{collection}:{item_id}")
            self._after_change(s, coll.stage, f"{item_id} was edited")
            return copy.deepcopy(s)

    def delete_item(self, sid: str, collection: str, item_id: str) -> dict:
        with self.lock:
            s = self._get(sid)
            self._require_idle(s)
            coll, items, index = self._find(s, collection, item_id)
            item = items.pop(index)
            meta = s["items"][f"{collection}:{item_id}"]
            meta["history"].append({"at": now(), "action": "deleted", "by": "user",
                                    "before": copy.deepcopy(item),
                                    "previous_status": meta["status"]})
            meta["status"] = "deleted"
            s["deleted"].setdefault(collection, []).append({"at": now(), "item": item})
            self._record_change(s, f"{collection}:{item_id}", "deleted", item, None)
            self._event(s, "edit", f"Deleted {item_id}", ref=f"{collection}:{item_id}")
            self._after_change(s, coll.stage, f"{item_id} was deleted")
            return copy.deepcopy(s)

    def restore_item(self, sid: str, collection: str, item_id: str) -> dict:
        with self.lock:
            s = self._get(sid)
            self._require_idle(s)
            coll = COLLECTIONS.get(collection)
            deleted = s["deleted"].get(collection, []) if coll else []
            index = next((i for i, d in enumerate(deleted) if d["item"][coll.id_key] == item_id),
                         None)
            if index is None:
                raise ApiError(404, f"{item_id} is not in the deleted {collection}.")
            item = deleted.pop(index)["item"]
            self._list(s, collection).append(item)
            meta = s["items"][f"{collection}:{item_id}"]
            last = next((h for h in reversed(meta["history"]) if h["action"] == "deleted"), {})
            meta["status"] = last.get("previous_status", "proposed")
            meta["history"].append({"at": now(), "action": "restored", "by": "user",
                                    "after": copy.deepcopy(item)})
            self._record_change(s, f"{collection}:{item_id}", "restored", None, item)
            self._event(s, "edit", f"Restored {item_id}", ref=f"{collection}:{item_id}")
            self._after_change(s, coll.stage, f"{item_id} was restored")
            return copy.deepcopy(s)

    def accept(self, sid: str, collection: str, item_ids: list[str] | None = None) -> dict:
        """Accept the given items, or every proposed item in the collection.

        `collection` may also be singleton:sson or singleton:situation.
        """
        with self.lock:
            s = self._get(sid)
            self._require_idle(s)
            if collection.startswith("singleton:"):
                keys = [collection] if collection in s["items"] else []
            elif collection in COLLECTIONS:
                keys = [f"{collection}:{i}" for i in item_ids] if item_ids is not None else [
                    k for k, m in s["items"].items()
                    if k.startswith(f"{collection}:") and m["status"] == "proposed"]
            else:
                raise ApiError(404, f"Unknown collection {collection}.")
            accepted = []
            for key in keys:
                meta = s["items"].get(key)
                if meta is None or meta["status"] in ("deleted", "accepted"):
                    continue
                meta["history"].append({"at": now(), "action": "accepted", "by": "user",
                                        "previous_status": meta["status"]})
                meta["status"] = "accepted"
                accepted.append(key.split(":", 1)[1])
            if accepted:
                self._event(s, "review", f"Accepted {', '.join(accepted)}", refs=keys)
                self._save(s)
            return copy.deepcopy(s)

    def edit_singleton(self, sid: str, name: str, fields: dict) -> dict:
        with self.lock:
            s = self._get(sid)
            self._require_idle(s)
            if name not in SINGLETONS:
                raise ApiError(404, f"Unknown record {name}.")
            allowed, stage = SINGLETONS[name]
            unknown = set(fields) - set(allowed)
            if unknown:
                raise ApiError(422, f"{name} has no field(s) {', '.join(sorted(unknown))}.")
            intent = s["state"].setdefault("captured_intent", {})
            clean = {}
            for field, value in fields.items():
                text = str(value or "").strip() if field == "single_statement_intent" else _text(value)
                clean[field] = (text or None) if field in _OPTIONAL_TEXT else text
            if "single_statement_intent" in clean and not clean["single_statement_intent"]:
                raise ApiError(422, "The SSON cannot be empty.")
            before = {f: intent.get(f) for f in allowed}
            intent.update(clean)
            after = {f: intent.get(f) for f in allowed}
            if after == before:
                return copy.deepcopy(s)
            key = f"singleton:{name}"
            meta = s["items"].setdefault(key, {"status": "added", "origin": "user",
                                               "original": None, "history": []})
            if meta["origin"] == "ai":
                meta["status"] = "edited"
            meta["history"].append({"at": now(), "action": "edited", "by": "user",
                                    "before": before, "after": after})
            label = "SSON" if name == "sson" else "current situation"
            self._record_change(s, key, "edited", before, after)
            self._event(s, "edit", f"Edited the {label}", ref=key)
            self._after_change(s, stage, f"The {label} was edited")
            return copy.deepcopy(s)

    def dismiss_stale(self, sid: str, stage: str) -> dict:
        with self.lock:
            s = self._get(sid)
            self._require_idle(s)
            if s["stages"].get(stage, {}).get("status") == "stale":
                s["stages"][stage].update(status="done", stale_reason=None)
                self._event(s, "review", f"Kept {pipeline.STAGE_LABELS[stage]} output as is",
                            stage=stage)
                self._save(s)
            return copy.deepcopy(s)

    # Impact analysis --------------------------------------------------------------

    def _record_change(self, s: dict, key: str, action: str, before, after) -> None:
        """Each manual edit waits here until an impact analysis covers it."""
        s["changes"].append({"change_id": f"C-{len(s['changes']) + 1}", "at": now(),
                             "key": key, "action": action, "before": copy.deepcopy(before),
                             "after": copy.deepcopy(after), "analyzed_in": None})

    def analyze_impact(self, sid: str) -> dict:
        """Start the impact analysis agent on every edit not analyzed yet."""
        with self.lock:
            s = self._get(sid)
            self._require_idle(s)
            pending = [c for c in s["changes"] if not c["analyzed_in"]]
            if not pending:
                raise ApiError(422, "There are no edits to analyze since the last impact analysis.")
            report_id = f"R-{len(s['impact_reports']) + 1}"
            s["running"] = True
            s["run"] = {"impact": report_id, "change_ids": [c["change_id"] for c in pending]}
            self._event(s, "impact", f"Impact analysis {report_id} started for "
                                     f"{len(pending)} edit(s)")
            self._save(s)
            threading.Thread(target=self._run_impact, args=(sid,), daemon=True).start()
            return copy.deepcopy(s)

    def _run_impact(self, sid: str) -> None:
        from agentic_flow.impact_analysis.graph import build_impact_analysis

        with self.lock:
            s = self.sessions[sid]
            run = s["run"]
            changes = [c for c in s["changes"] if c["change_id"] in run["change_ids"]]
            state = copy.deepcopy({**s["state"], "impact_request": {"changes": changes}})
        try:
            with self.run_lock:
                result = build_impact_analysis().invoke(state)["impact_report"]
            with self.lock:
                report = {"report_id": run["impact"], "at": now(), "status": "open",
                          "change_ids": run["change_ids"],
                          **{k: result.get(k, []) for k in ("changes", "candidates", "proposals",
                                                            "unaffected", "notes", "stages")}}
                s["impact_reports"].append(report)
                for change in s["changes"]:
                    if change["change_id"] in run["change_ids"]:
                        change["analyzed_in"] = report["report_id"]
                self._event(s, "impact", f"Impact analysis {report['report_id']}: "
                                         f"{len(report['proposals'])} suggestion(s), "
                                         f"{len(report['unaffected'])} unaffected")
        except Exception as exc:  # report it in the UI, keep the edits pending
            with self.lock:
                self._event(s, "error", f"Impact analysis failed: {type(exc).__name__}: {exc}")
        finally:
            with self.lock:
                s["running"] = False
                s.pop("run", None)
                self._save(s)

    def _report(self, s: dict, report_id: str) -> dict:
        report = next((r for r in s["impact_reports"] if r["report_id"] == report_id), None)
        if report is None:
            raise ApiError(404, f"No impact report {report_id}.")
        return report

    def decide_proposal(self, sid: str, report_id: str, proposal_id: str, decision: str) -> dict:
        """Accept (apply through the normal validated edit) or reject one suggestion."""
        if decision not in ("accept", "reject"):
            raise ApiError(422, "Decision must be accept or reject.")
        with self.lock:
            s = self._get(sid)
            self._require_idle(s)
            report = self._report(s, report_id)
            proposal = next((p for p in report["proposals"] if p["proposal_id"] == proposal_id), None)
            if proposal is None:
                raise ApiError(404, f"No suggestion {proposal_id} in {report_id}.")
            if proposal["status"] != "pending":
                raise ApiError(409, f"{proposal_id} was already {proposal['status']}.")
            if decision == "reject":
                proposal["status"] = "rejected"
                self._event(s, "review", f"Rejected {report_id} {proposal_id}")
                self._save(s)
                return copy.deepcopy(s)

            kind, collection = proposal["kind"], proposal["collection"]
            if kind == "rerun":
                proposal["status"] = "accepted"
                self._event(s, "review", f"Accepted {report_id} {proposal_id}: rebuild "
                                         f"{pipeline.STAGE_LABELS[proposal['stage']]}")
                return self.rerun(sid, proposal["stage"], False)
            first_new = len(s["changes"])
            if kind in ("revise", "unlink") and collection.startswith("singleton:"):
                self.edit_singleton(sid, collection.split(":", 1)[1], proposal["fields"])
            elif kind in ("revise", "unlink"):
                self.edit_item(sid, collection, proposal["artifact_id"], proposal["fields"])
            elif kind == "remove":
                self.delete_item(sid, collection, proposal["artifact_id"])
            elif kind == "add":
                self.add_item(sid, collection, proposal["fields"])
            # an accepted suggestion is part of this analysis, not a new edit to analyze
            for change in s["changes"][first_new:]:
                change["analyzed_in"] = report_id
                change["via"] = proposal_id
            proposal["status"] = "accepted"
            self._event(s, "review", f"Accepted {report_id} {proposal_id}",
                        ref=proposal["key"] or None)
            self._save(s)
            return copy.deepcopy(s)

    def close_report(self, sid: str, report_id: str) -> dict:
        """Close a report; the stages it covered are no longer out of date."""
        with self.lock:
            s = self._get(sid)
            self._require_idle(s)
            report = self._report(s, report_id)
            report["status"] = "closed"
            rebuilt = {p["stage"] for p in report["proposals"]
                       if p["kind"] == "rerun" and p["status"] == "accepted"}
            cleared = []
            for stage in report.get("stages", []):
                if stage not in rebuilt and s["stages"].get(stage, {}).get("status") == "stale":
                    s["stages"][stage].update(status="done", stale_reason=None)
                    cleared.append(pipeline.STAGE_LABELS[stage])
            self._event(s, "review", f"Closed impact analysis {report_id}"
                        + (f"; reviewed {', '.join(cleared)}" if cleared else ""))
            self._save(s)
            return copy.deepcopy(s)

    # Runs -------------------------------------------------------------------------

    def create(self, prd: str) -> dict:
        if not prd.strip():
            raise ApiError(422, "Paste a PRD first.")
        sid = uuid.uuid4().hex[:10]
        stamp = now()
        session = {
            "id": sid, "created_at": stamp, "updated_at": stamp,
            "running": False,
            "state": {"prd": prd},
            "stages": {name: {"status": "pending", "label": pipeline.STAGE_LABELS[name],
                              "started_at": None, "finished_at": None, "error": None,
                              "stale_reason": None}
                       for name in pipeline.STAGES},
            "items": {}, "deleted": {}, "snapshots": [], "events": [],
            "changes": [], "impact_reports": [],
        }
        with self.lock:
            self.sessions[sid] = session
            self._start(session, None, "Pipeline started")
            return copy.deepcopy(session)

    def rerun(self, sid: str, stage: str, cascade: bool) -> dict:
        if stage not in pipeline.MODEL_STAGES:
            raise ApiError(422, f"Cannot re-run {stage}.")
        with self.lock:
            s = self._get(sid)
            self._require_idle(s)
            stages = [stage]
            if cascade:
                downstream = set(pipeline.DOWNSTREAM[stage])
                stages += [st for st in pipeline.MODEL_STAGES if st in downstream]
            for st in stages:
                self._reset(s, st, f"Re-run of {pipeline.STAGE_LABELS[stage]}")
            self._start(s, stages, f"Re-run: {', '.join(pipeline.STAGE_LABELS[x] for x in stages)}")
            return copy.deepcopy(s)

    def _start(self, s: dict, stages: list[str] | None, detail: str) -> None:
        planned = stages or pipeline.STAGES
        s["running"] = True
        s["run"] = {"planned": planned, "prior": {st: s["stages"][st]["status"] for st in planned},
                    "full": stages is None}
        for st in planned:
            s["stages"][st].update(status="queued", error=None, stale_reason=None)
        s["stages"][planned[0]].update(status="running", started_at=now())
        self._event(s, "run", detail, stages=planned)
        self._save(s)
        threading.Thread(target=self._run, args=(s["id"],), daemon=True).start()

    def _run(self, sid: str) -> None:
        with self.lock:
            s = self.sessions[sid]
            run = s["run"]
        last = {"at": datetime.now(timezone.utc)}

        def on_update(changes: dict) -> None:
            with self.lock:
                s["state"].update(copy.deepcopy(changes))

        def on_node(node: str) -> None:
            stage = pipeline.NODE_STAGE[node]
            with self.lock:
                at = datetime.now(timezone.utc)
                ms = int((at - last["at"]).total_seconds() * 1000)
                last["at"] = at
                self._event(s, "node", f"{node} finished", node=node, stage=stage, ms=ms)
                if node == pipeline.LAST_NODE[stage] and stage in run["planned"]:
                    s["stages"][stage].update(status="done", finished_at=now())
                    self._register(s, stage)
                    later = run["planned"][run["planned"].index(stage) + 1:]
                    if later:
                        s["stages"][later[0]].update(status="running", started_at=now())
                self._save(s)

        try:
            with self.run_lock:
                if run["full"]:
                    pipeline.run_full(copy.deepcopy(s["state"]), on_update, on_node)
                else:
                    def get_state() -> dict:
                        with self.lock:
                            return copy.deepcopy(s["state"])
                    pipeline.run_stages(run["planned"], get_state, on_update, on_node)
        except Exception as exc:  # report any failure in the UI, keep the session
            with self.lock:
                message = f"{type(exc).__name__}: {exc}"
                for st in run["planned"]:
                    stage = s["stages"][st]
                    if stage["status"] == "running":
                        stage.update(status="error", error=message)
                    elif stage["status"] == "queued":
                        prior = run["prior"][st]
                        stage.update(status="stale" if prior in ("done", "stale") else "pending",
                                     stale_reason="An earlier stage failed during the re-run."
                                     if prior in ("done", "stale") else None)
                self._event(s, "error", message)
        else:
            with self.lock:
                if not run["full"]:
                    ran = set(run["planned"])
                    stale = {d for st in run["planned"] for d in pipeline.DOWNSTREAM[st]} - ran
                    self._mark_stale(s, [st for st in pipeline.MODEL_STAGES if st in stale],
                                     f"{', '.join(pipeline.STAGE_LABELS[x] for x in run['planned'])} re-ran")
                self._event(s, "run", "Run finished")
        finally:
            with self.lock:
                self._refresh_trace(s)
                s["running"] = False
                s.pop("run", None)
                self._save(s)
