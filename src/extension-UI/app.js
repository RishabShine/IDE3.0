/* IDE3.0 extension UI: one PRD in, five pages of traceable artifacts out.
   Talks to agentic_flow/api/server.py. Plain JS, no build step. */
"use strict";

const FLAG = "\u{1F6A9}";
const ICONS = {
  welcome: '<path d="M4 4h10l6 6v10H4z"/><path d="M14 4v6h6M8 14h8M8 17h5"/>',
  intent: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="1" fill="currentColor"/>',
  situation: '<path d="M4 19h16M6 16V9M10 16V5M14 16v-5M18 16V8"/>',
  stakeholders: '<circle cx="9" cy="8" r="3"/><path d="M3 19c0-3.3 2.7-6 6-6s6 2.7 6 6"/><circle cx="17" cy="9" r="2.3"/><path d="M16 13.2c2.8 0 5 2.3 5 5"/>',
  personas: '<rect x="4" y="4" width="16" height="16" rx="2"/><circle cx="12" cy="10" r="2.6"/><path d="M7.5 17c.8-2 2.5-3 4.5-3s3.7 1 4.5 3"/>',
  goals: '<path d="M5 21V4"/><path d="M5 4h11l-2 4 2 4H5"/>',
  usecases: '<ellipse cx="15.5" cy="12" rx="6.5" ry="4.5"/><circle cx="5" cy="6.5" r="1.8"/><path d="M5 8.3v5.2M2.3 10.5h5.4M5 13.5l-2.3 4.5M5 13.5l2.3 4.5"/>',
  trace: '<circle cx="5" cy="6" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="12" cy="18" r="2"/><path d="M7 6h10M6 8l5 8.3M18 8l-5 8.3"/>',
};
const PAGES = [
  { id: "welcome", title: "Welcome", sub: "PRD input", file: "prd.md", stages: [] },
  { id: "intent", title: "Capture intent", sub: "SSON · G.1", file: "intent.sson", stages: ["sson", "sson_eval"] },
  { id: "situation", title: "Situation & benefits", sub: "G.2 · G.3 · E.5 · E.6", file: "intent.pegs", stages: ["context"] },
  { id: "stakeholders", title: "Stakeholders", sub: "User modelling", file: "stakeholders.json", stages: ["stakeholders"] },
  { id: "personas", title: "Personas", sub: "User modelling · MSF", file: "personas.msf", stages: ["personas"] },
  { id: "goals", title: "Goals", sub: "Hard · soft goals", file: "goals.json", stages: ["goals"] },
  { id: "usecases", title: "Use cases", sub: "L13 · use case model", file: "use-cases.uml", stages: ["use_cases"] },
  { id: "trace", title: "Trace", sub: "Artifact graph", file: "artifact-graph", stages: ["trace"] },
];
const PAGE = Object.fromEntries(PAGES.map((p) => [p.id, p]));

const CONTEXT_SECTIONS = [
  { coll: "problems", title: "Problems", code: "G.2", lede: "What goes wrong today. Benefits link back to these." },
  { coll: "benefits", title: "Expected benefits", code: "G.3", lede: "What improves, linked to the problems it fixes. Hard benefits carry a measure from the PRD." },
  { coll: "effects", title: "Effects", code: "E.5", lede: "Changes to the environment the project expects to cause." },
  { coll: "invariants", title: "Invariants", code: "E.6", lede: "Properties of the environment that must keep holding." },
  { coll: "constraints", title: "Constraints", code: "E.3", lede: "Fixed conditions the solution must work within." },
  { coll: "scope_exclusions", title: "Scope exclusions", code: "G.6", lede: "What the PRD says this project will not do." },
];
const COLL_LABEL = {
  problems: "problem", benefits: "benefit", effects: "effect", invariants: "invariant",
  constraints: "constraint", scope_exclusions: "scope exclusion", stakeholders: "stakeholder", personas: "persona",
  goals: "goal",
};
const COLL_PAGE = { stakeholders: "stakeholders", personas: "personas", goals: "goals", usecases: "usecases" };
const textOf = (item) => item.description ?? item.statement ?? "";
const STATUS = {
  proposed: ["info", "AI proposed"], accepted: ["ok", "Accepted"], edited: ["warn", "Edited"],
  added: ["violet", "Added by you"], deleted: ["bad", "Deleted"],
};
const PERSONA_FIELDS = [
  ["status_and_trust_level", "Status & trust level"], ["demographics", "Demographics"],
  ["ksa", "Knowledge, skills, abilities"], ["gmc", "Goals, motives, concerns"], ["usage_patterns", "Usage patterns"],
];
const CRITERIA = {
  clear_and_concise: "Clear and concise", goal_and_how: "States the goal and how",
  names_capability: "Names the capability", need_not_want: "A need, not a want", success_condition: "Has a success condition",
};

const S = {
  config: null, session: null, sessions: [], page: "welcome", tabs: ["welcome"],
  composing: false, prd: "",
  editing: null, formError: null, showDeleted: new Set(),
  traceTab: "graph", selected: null, covSelected: null, pollTimer: null,
  traceHidden: new Set(), traceShowLong: false,
};

/* ---------- helpers ---------- */
const $ = (sel) => document.querySelector(sel);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const isFlagged = (t) => String(t || "").trim().startsWith(FLAG);
const unflag = (t) => String(t || "").trim().replace(new RegExp("^" + FLAG + "\\s*", "u"), "");
const time = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "");
const dateTime = (iso) => (iso ? new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "");
const running = () => !!S.session?.running;
const dis = () => (running() ? "disabled" : "");
const st = () => S.session?.state || {};
const intent = () => st().captured_intent || {};
const meta = (key) => S.session?.items?.[key];
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;

function list(coll) {
  if (coll === "stakeholders") return st().stakeholder_metadata?.stakeholders || [];
  if (coll === "personas") return st().persona_metadata?.personas || [];
  if (coll === "goals") return st().goal_metadata?.goals || [];
  return intent()[coll] || [];
}
function idOf(coll, item) {
  return item[S.config.collections[coll].id_key];
}
function pageOfKey(key) {
  if (key === "singleton:sson") return "intent";
  if (key === "singleton:situation") return "situation";
  return COLL_PAGE[key.split(":")[0]] || "situation";
}
function stageStatus(stage) {
  return S.session?.stages?.[stage]?.status || "pending";
}
function pageStatus(page) {
  const statuses = PAGE[page].stages.map(stageStatus);
  if (page === "welcome") return S.session ? "done" : "pending";
  for (const s of ["error", "running", "stale", "queued"]) if (statuses.includes(s)) return s;
  return statuses.length && statuses.every((s) => s === "done") ? "done" : "pending";
}

async function api(method, path, body) {
  const res = await fetch(path, {
    method, headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg).join("; ") : res.statusText);
  }
  return data;
}

function toast(msg, bad = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast show" + (bad ? " bad" : "");
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (el.className = "toast"), bad ? 5000 : 2600);
}

function confirmModal({ title, body, ok = "Continue", danger = false }) {
  return new Promise((resolve) => {
    const root = $("#modal");
    root.innerHTML = `<div class="modal-back"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="mTitle">
      <h2 id="mTitle">${esc(title)}</h2><p>${body}</p>
      <div class="actions"><button class="btn" data-m="0">Cancel</button>
      <button class="btn ${danger ? "bad" : "primary"}" data-m="1">${esc(ok)}</button></div></div></div>`;
    const done = (v) => { root.innerHTML = ""; resolve(v); };
    root.querySelector(".modal-back").addEventListener("click", (e) => {
      if (e.target.dataset.m !== undefined) done(e.target.dataset.m === "1");
      else if (e.target.classList.contains("modal-back")) done(false);
    });
    root.querySelector('[data-m="1"]').focus();
  });
}

function store(key, value) {
  try { value === null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch (_) { /* private mode */ }
}
function recall(key) {
  try { return localStorage.getItem(key); } catch (_) { return null; }
}

/* ---------- data flow ---------- */
function setSession(session) {
  S.session = session;
  if (session) store("ide3.session", session.id);
  render();
  schedulePoll();
}

function schedulePoll() {
  clearTimeout(S.pollTimer);
  if (!running()) return;
  S.pollTimer = setTimeout(async () => {
    try {
      const fresh = await api("GET", `/api/sessions/${S.session.id}`);
      const wasRunning = running();
      setSession(fresh);
      if (wasRunning && !fresh.running) {
        const err = Object.values(fresh.stages).find((x) => x.status === "error");
        err ? toast(`Run failed: ${err.error}`, true) : toast("Run finished");
        refreshSessions();
      }
    } catch (e) {
      toast(e.message, true);
      S.pollTimer = setTimeout(schedulePoll, 2000);
    }
  }, 700);
}

async function refreshSessions() {
  try { S.sessions = await api("GET", "/api/sessions"); render(); } catch (_) { /* shown elsewhere */ }
}

async function mutate(method, path, body, okMsg) {
  try {
    const session = await api(method, path, body);
    S.editing = null;
    S.formError = null;
    setSession(session);
    if (okMsg) toast(okMsg);
    return true;
  } catch (e) {
    S.formError = e.message;
    if (S.editing) render(); else toast(e.message, true);
    return false;
  }
}

/* ---------- navigation ---------- */
function go(page, focusKey) {
  if (!PAGE[page]) page = "welcome";
  S.page = page;
  if (!S.tabs.includes(page)) S.tabs.push(page);
  if (location.hash !== "#" + page) history.replaceState(null, "", "#" + page);
  render();
  $("#view").scrollTop = 0;
  if (focusKey) requestAnimationFrame(() => flash(focusKey));
}
function flash(key) {
  const el = document.getElementById("card-" + key);
  if (!el) return;
  el.scrollIntoView({ block: "center", behavior: "smooth" });
  el.classList.remove("flash");
  void el.offsetWidth;
  el.classList.add("flash");
}
function jump(key) {
  const page = pageOfKey(key);
  if (page !== S.page) go(page, key); else flash(key);
}

/* ---------- chrome ---------- */
function render() {
  if (!S.config) return;
  const view = $("#view");
  const scroll = view.scrollTop;
  renderChrome();
  view.innerHTML = `<section class="screen">${impactBanner()}${PAGE_RENDER[S.page]()}</section>`;
  view.scrollTop = scroll;
  if (S.page === "trace" && S.traceTab === "graph") requestAnimationFrame(drawEdges);
}

function renderChrome() {
  const prdTitle = (st().prd || "").split("\n").find((l) => l.trim())?.trim();
  $("#title").textContent = prdTitle ? `${prdTitle} · IDE3.0` : "IDE3.0 · Requirements";
  $("#titleTag").textContent = S.session ? `session ${S.session.id}` : "Extension UI";

  $("#activity").innerHTML = PAGES.map((p) => {
    const status = pageStatus(p.id);
    const dot = ["stale", "error", "running"].includes(status) ? `<span class="dot ${status}"></span>` : "";
    return `<button class="ico ${S.page === p.id ? "on" : ""}" data-act="nav" data-page="${p.id}" title="${esc(p.title)}" aria-label="${esc(p.title)}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">${ICONS[p.id]}</svg>${dot}</button>`;
  }).join("");

  const counts = summaryCounts();
  $("#sidebar").innerHTML = `
    <div class="side-head"><b>IDE3.0</b><span>Requirements flow</span></div>
    <div class="section-label">Pages</div>
    <ul class="steps">${PAGES.map((p, i) => {
      const status = pageStatus(p.id);
      const num = status === "done" ? "✓" : status === "error" ? "!" : status === "stale" ? "↻" : i;
      return `<li><button class="${status} ${S.page === p.id ? "on" : ""}" data-act="nav" data-page="${p.id}">
        <span class="num">${num}</span><span><span class="name">${esc(p.title)}</span><span class="sub">${esc(p.sub)}</span></span>
        ${pageBadge(p.id, status)}</button></li>`;
    }).join("")}</ul>
    <div class="divider"></div>
    <div class="section-label">Artifacts</div>
    <div class="model-sum">
      <span>Problems</span><b>${counts.problems}</b>
      <span>Benefits</span><b>${counts.benefits}</b>
      <span>Effects · invariants</span><b>${counts.effects} · ${counts.invariants}</b>
      <span>Constraints · exclusions</span><b>${counts.constraints} · ${counts.scope_exclusions}</b>
      <span>Stakeholders</span><b>${counts.stakeholders}</b>
      <span>Personas</span><b>${counts.personas}</b>
      <span>Goals</span><b>${counts.goals}</b>
      <span>Use cases</span><b>${(st().use_case_metadata?.use_cases || []).length}</b>
    </div>
    <div class="divider"></div>
    <div class="section-label">Review</div>
    <div class="model-sum">
      <span>Awaiting review</span><b class="${counts.proposed ? "warn" : ""}">${counts.proposed}</b>
      <span>Accepted</span><b>${counts.accepted}</b>
      <span>Edited · added</span><b>${counts.edited} · ${counts.added}</b>
      <span>Red-flagged</span><b class="${counts.flagged ? "warn" : ""}">${counts.flagged}</b>
      <span>Trace gaps</span><b class="${counts.gaps ? "bad" : ""}">${counts.gaps}</b>
    </div>
    <div class="side-foot">
      ${S.session ? `Session <span class="mono">${esc(S.session.id)}</span> · saved in <span class="mono">.ide3/sessions</span>` : "No session yet"}
      <button class="btn" data-act="new-session" ${dis()}>New PRD</button>
    </div>`;

  $("#tabs").innerHTML = S.tabs.map((id) => `<button class="tab ${S.page === id ? "on" : ""}" data-act="nav" data-page="${id}">
    <span class="mono">${esc(PAGE[id].file)}</span>${S.tabs.length > 1 ? `<span class="x" data-act="close-tab" data-page="${id}" aria-label="Close">×</span>` : ""}</button>`).join("");

  const status = $("#status");
  const errored = S.session && Object.values(S.session.stages).some((x) => x.status === "error");
  status.className = "status " + (running() ? "running" : errored ? "error" : S.session ? "ready" : "");
  const runningStage = S.session && Object.values(S.session.stages).find((x) => x.status === "running");
  const last = S.session?.events?.at(-1);
  status.innerHTML = `<span>IDE3.0</span><span>${esc(S.config.model)}</span>
    <span class="grow"></span>
    <span>${running() ? (S.session.run?.impact ? "Analyzing impact" : `Running: ${esc(runningStage?.label || "…")}`) : errored ? "Last run failed" : S.session ? "Ready" : ""}</span>
    ${last ? `<span>${esc(time(last.at))} · ${esc(last.detail)}</span>` : ""}`;
}

function pageBadge(page, status) {
  if (status === "stale") return '<span class="badge warn">stale</span>';
  if (status === "error") return '<span class="badge bad">error</span>';
  if (status === "running") return '<span class="badge info">running</span>';
  if (!S.session || status === "pending" || status === "queued") return "";
  const n = (colls) => colls.reduce((a, c) => a + list(c).length, 0);
  const proposed = (colls) => colls.reduce((a, c) => a + list(c).filter((i) => meta(`${c}:${idOf(c, i)}`)?.status === "proposed").length, 0);
  const review = (colls) => {
    const p = proposed(colls);
    return p ? `<span class="badge warn" title="Awaiting review">${p} to review</span>` : `<span class="badge ok">${n(colls)}</span>`;
  };
  if (page === "intent") {
    const ev = intent().sson_evaluation;
    return ev ? `<span class="badge ${ev.passed ? "ok" : "warn"}">${ev.score}/100</span>` : "";
  }
  if (page === "situation") return review(CONTEXT_SECTIONS.map((s) => s.coll));
  if (page === "stakeholders") return review(["stakeholders"]);
  if (page === "personas") return review(["personas"]);
  if (page === "goals") return review(["goals"]);
  if (page === "usecases") {
    const m = st().use_case_metadata;
    if (!m) return "";
    return m.issues?.length ? `<span class="badge warn" title="Model checks">${plural(m.issues.length, "check")}</span>` : `<span class="badge ok">${m.use_cases.length}</span>`;
  }
  if (page === "trace") {
    const g = st().artifact_graph?.gaps?.length || 0;
    return `<span class="badge ${g ? "bad" : "ok"}">${g ? plural(g, "gap") : "linked"}</span>`;
  }
  return "";
}

function summaryCounts() {
  const c = { proposed: 0, accepted: 0, edited: 0, added: 0, flagged: 0, gaps: st().artifact_graph?.gaps?.length || 0 };
  for (const coll of Object.keys(COLL_LABEL)) {
    const items = S.session ? list(coll) : [];
    c[coll] = items.length;
    for (const item of items) {
      const m = meta(`${coll}:${idOf(coll, item)}`);
      if (m && c[m.status] !== undefined) c[m.status]++;
      if (isFlagged(textOf(item))) c.flagged++;
    }
  }
  for (const key of ["singleton:sson", "singleton:situation"]) {
    const m = meta(key);
    if (m && c[m.status] !== undefined) c[m.status]++;
  }
  if (isFlagged(intent().single_statement_intent)) c.flagged++;
  return c;
}

/* ---------- shared blocks ---------- */
function statusPill(key) {
  const m = meta(key);
  if (!m) return "";
  const [cls, label] = STATUS[m.status] || ["neutral", m.status];
  return `<span class="pill ${cls}">${label}</span>`;
}
function flagPill(text) {
  return isFlagged(text) ? `<span class="pill warn" title="The PRD does not state this; the model derived it">${FLAG} Not in PRD</span>` : "";
}

function stageBanners(stages) {
  if (!S.session) return "";
  return stages.map((stage) => {
    const s = S.session.stages[stage];
    if (!s) return "";
    const down = S.config.downstream[stage] || [];
    if (s.status === "running" || s.status === "queued")
      return `<div class="banner running"><span class="spinner"></span><div class="msg"><b>${esc(s.label)}</b>${s.status === "running" ? "Running now…" : "Queued, waiting for the stages before it."}</div></div>`;
    if (s.status === "error")
      return `<div class="banner error"><div class="msg"><b>${esc(s.label)} failed</b><span class="mono">${esc(s.error)}</span></div>
        <button class="btn" data-act="rerun" data-stage="${stage}" ${dis()}>Retry</button>
        ${down.length ? `<button class="btn" data-act="rerun" data-stage="${stage}" data-cascade="1" ${dis()}>Retry with downstream</button>` : ""}</div>`;
    if (s.status === "stale")
      return `<div class="banner stale"><div class="msg"><b>${esc(s.label)} is out of date</b>${esc(s.stale_reason || "An upstream artifact changed")} after this output was produced.</div>
        <button class="btn primary" data-act="rerun" data-stage="${stage}" ${dis()}>Re-run</button>
        ${down.length ? `<button class="btn" data-act="rerun" data-stage="${stage}" data-cascade="1" ${dis()}>Re-run with downstream</button>` : ""}
        <button class="btn ghost" data-act="keep" data-stage="${stage}" ${dis()}>Keep as is</button></div>`;
    return "";
  }).join("");
}

function noRun(page) {
  if (S.session) return "";
  return `<div class="card"><div class="empty">Nothing here yet. Paste a PRD on the <button class="chip" data-act="nav" data-page="welcome">Welcome</button> page and run the flow; ${esc(page)} fill in as it runs.</div></div>`;
}

function itemActions(coll, id, key) {
  const m = meta(key);
  return `<span class="grow"></span><span class="actions">
    ${m && m.status !== "accepted" ? `<button class="btn ok" data-act="accept" data-coll="${coll}" data-id="${esc(id)}" ${dis()}>Accept</button>` : ""}
    <button class="btn" data-act="edit" data-key="${esc(key)}" ${dis()}>Edit</button>
    <button class="btn ghost bad" data-act="delete" data-coll="${coll}" data-id="${esc(id)}" ${dis()} aria-label="Delete ${esc(id)}">Delete</button></span>`;
}

function sourceBlock(item, key) {
  if (item.source) return `<div class="quote"><span class="kind">PRD</span>“${esc(item.source)}”</div>`;
  const origin = meta(key)?.origin === "user" ? "Added by you, with no PRD quote" : "No PRD quote supports this; the model derived it";
  return `<div class="quote missing">${esc(origin)}</div>`;
}

/* ---------- item cards ---------- */
function goalChips(match, label, quietWhenEmpty = false) {
  if (!st().goal_metadata) return "";
  const goals = list("goals").filter(match);
  if (!goals.length && quietWhenEmpty) return "";
  return `<div class="links"><span class="kind">${label}</span>${goals.length ? goals.map((g) => `<button class="chip" data-act="jump" data-key="goals:${esc(g.goal_id)}">${esc(g.goal_id)}</button>`).join("") : '<span class="faint small">none</span>'}</div>`;
}
function actorRow(a = {}) {
  return `<div class="actor-row">
    <input class="input" data-actor="name" placeholder="Name" aria-label="Actor name" value="${esc(a.name || "")}">
    <select class="input" data-actor="stakeholder_id" aria-label="Stakeholder"><option value="">Not a stakeholder</option>
      ${list("stakeholders").map((x) => `<option value="${esc(x.stakeholder_id)}" ${a.stakeholder_id === x.stakeholder_id ? "selected" : ""}>${esc(x.stakeholder_id)} · ${esc(x.name)}</option>`).join("")}</select>
    <input class="input" data-actor="role" placeholder="Role" aria-label="Role" value="${esc(a.role || "")}">
    <input class="input" data-actor="involvement" placeholder="Involvement in this goal" aria-label="Involvement" value="${esc(a.involvement || "")}">
    <button type="button" class="btn ghost bad" data-act="remove-actor" aria-label="Remove actor">×</button></div>`;
}
function itemCard(coll, item) {
  const id = idOf(coll, item);
  const key = `${coll}:${id}`;
  if (S.editing === key) return editCard(coll, item, key);
  const status = meta(key)?.status || "proposed";
  let head = "", body = "";
  if (coll === "stakeholders") {
    const reps = list("personas").filter((p) => p.stakeholder_id === id);
    head = `<span class="item-title">${esc(item.name)}</span>${item.involvement ? `<span class="pill ${item.involvement === "direct" ? "info" : "neutral"}">${esc(item.involvement)}</span>` : '<span class="pill neutral">involvement unknown</span>'}`;
    body = `<div class="item-text">${esc(item.summary)}</div>
      ${item.justification ? `<div class="quote"><span class="kind">Why</span>${esc(item.justification)}</div>` : ""}
      ${goalChips((g) => (g.actors || []).some((a) => a.stakeholder_id === id), "Acts in goals")}
      <div class="links"><span class="kind">Represented by</span>${reps.length ? reps.map((p) => `<button class="chip" data-act="jump" data-key="personas:${esc(p.persona_id)}">${esc(p.persona_id)}</button>`).join("") : `<span class="${item.involvement === "direct" ? "pill warn" : "faint"}">${item.involvement === "direct" ? "No persona (trace gap)" : "none"}</span>`}</div>`;
  } else if (coll === "personas") {
    const sh = list("stakeholders").find((x) => x.stakeholder_id === item.stakeholder_id);
    head = `<span class="item-title">${esc(item.name || item.role || "Unnamed persona")}</span>${item.name && item.role ? `<span class="muted small">${esc(item.role)}</span>` : ""}`;
    body = `<div class="links"><span class="kind">Represents</span>${sh ? `<button class="chip" data-act="jump" data-key="stakeholders:${esc(sh.stakeholder_id)}">${esc(sh.stakeholder_id)}</button> <span class="small muted">${esc(sh.name)}</span>` : '<span class="pill warn">No stakeholder link (trace gap)</span>'}</div>
      <div class="fields">${PERSONA_FIELDS.map(([f, label]) => `<div class="field"><span class="kind">${label}</span><div class="v ${item[f] ? "" : "none"}">${esc(item[f] || "Not in the PRD")}</div></div>`).join("")}</div>`;
  } else if (coll === "goals") {
    const benefitIds = new Set(list("benefits").map((b) => b.id));
    const holders = new Map(list("stakeholders").map((x) => [x.stakeholder_id, x]));
    const type = item.goal_type;
    head = `${flagPill(item.statement)}<span class="pill ${type === "hard" ? "ok" : type === "soft" ? "violet" : "neutral"}">${esc(type || "type unclear")}</span>`;
    const actors = item.actors || [];
    body = `<div class="item-text">${esc(unflag(item.statement))}</div>
      <div class="links"><span class="kind">Delivers</span>${(item.benefit_ids || []).length ? item.benefit_ids.map((b) => benefitIds.has(b) ? `<button class="chip" data-act="jump" data-key="benefits:${esc(b)}">${esc(b)}</button>` : `<span class="chip dangling" title="This benefit no longer exists">${esc(b)}</span>`).join("") : '<span class="faint small">no benefit</span>'}</div>
      ${actors.length ? `<table class="actors"><thead><tr><th>Actor</th><th>Stakeholder</th><th>Role</th><th>Involvement</th></tr></thead><tbody>
        ${actors.map((a) => `<tr><td>${esc(a.name)}</td><td>${a.stakeholder_id ? (holders.has(a.stakeholder_id) ? `<button class="chip" data-act="jump" data-key="stakeholders:${esc(a.stakeholder_id)}">${esc(a.stakeholder_id)}</button>` : `<span class="chip dangling">${esc(a.stakeholder_id)}</span>`) : '<span class="faint">not a stakeholder</span>'}</td><td>${esc(a.role) || '<span class="faint">—</span>'}</td><td class="muted">${esc(a.involvement) || '<span class="faint">—</span>'}</td></tr>`).join("")}</tbody></table>`
        : '<div class="links"><span class="kind">Actors</span><span class="faint small">none in the PRD</span></div>'}
      <div class="fields">
        <div class="field"><span class="kind">Plans</span><div class="v ${item.plans ? "" : "none"}">${esc(item.plans || "Not in the PRD")}</div></div>
        <div class="field"><span class="kind">Resources</span><div class="v ${(item.resources || []).length ? "" : "none"}">${(item.resources || []).length ? item.resources.map((r) => `<span class="pill neutral">${esc(r)}</span>`).join(" ") : "Not in the PRD"}</div></div>
        <div class="field"><span class="kind">Justification</span><div class="v ${item.justification ? "" : "none"}">${esc(item.justification || "Not in the PRD")}</div></div>
      </div>${sourceBlock(item, key)}`;
  } else {
    head = flagPill(item.description);
    body = `<div class="item-text">${esc(unflag(item.description))}</div>`;
    if (coll === "benefits") {
      const ids = new Set(list("problems").map((p) => p.id));
      body += `<div class="links"><span class="pill ${item.kind === "hard" ? "ok" : "neutral"}">${esc(item.kind)}</span>
        ${item.measure ? `<span class="small"><span class="kind">Measure</span> ${esc(item.measure)}</span>` : ""}
        ${goalChips((g) => (g.benefit_ids || []).includes(id), "Delivered by", true)}
        <span class="kind">Addresses</span>${(item.addresses || []).length ? item.addresses.map((p) => ids.has(p) ? `<button class="chip" data-act="jump" data-key="problems:${esc(p)}">${esc(p)}</button>` : `<span class="chip dangling" title="This problem no longer exists">${esc(p)}</span>`).join("") : '<span class="faint small">no problem</span>'}</div>`;
    }
    if (coll === "problems") {
      const by = list("benefits").filter((b) => (b.addresses || []).includes(id));
      const out = (intent().out_of_scope_problems || []).includes(id);
      body += `<div class="links">${out ? '<span class="pill neutral">Out of scope</span>' : ""}<span class="kind">Addressed by</span>
        ${by.length ? by.map((b) => `<button class="chip" data-act="jump" data-key="benefits:${esc(b.id)}">${esc(b.id)}</button>`).join("") : `<span class="${out ? "faint small" : "pill warn"}">${out ? "none" : "No benefit (trace gap)"}</span>`}</div>`;
    }
    body += sourceBlock(item, key);
  }
  const suggested = openSuggestions().get(key);
  const suggestion = suggested ? `<button class="pill warn" data-act="open-impact" title="Impact analysis suggests a change">${plural(suggested, "suggested change")}</button>` : "";
  return `<div class="item st-${status}" id="card-${esc(key)}">
    <div class="item-head"><span class="iid">${esc(id)}</span>${statusPill(key)}${suggestion}${head}${itemActions(coll, id, key)}</div>
    ${body}</div>`;
}

function formFields(coll, item) {
  const v = (f) => esc(f === "description" || f === "statement" ? unflag(item[f]) : Array.isArray(item[f]) ? item[f].join("\n") : item[f] ?? "");
  const ta = (f, label, hint = "", rows = 2) => `<label>${label}${hint ? ` <span class="hint">${hint}</span>` : ""}<textarea class="input" name="${f}" rows="${rows}">${v(f)}</textarea></label>`;
  const inp = (f, label, hint = "") => `<label>${label}${hint ? ` <span class="hint">${hint}</span>` : ""}<input class="input" name="${f}" value="${v(f)}"></label>`;
  if (coll === "stakeholders") {
    return inp("name", "Name") + `<label>Involvement<select class="input" name="involvement">
      ${["", "direct", "indirect"].map((o) => `<option value="${o}" ${(item.involvement || "") === o ? "selected" : ""}>${o || "Unknown"}</option>`).join("")}</select></label>`
      + ta("summary", "Summary") + ta("justification", "Justification", "why they are a stakeholder, ideally from the PRD");
  }
  if (coll === "personas") {
    return `<label>Represents stakeholder<select class="input" name="stakeholder_id"><option value="">No link</option>
      ${list("stakeholders").map((s) => `<option value="${esc(s.stakeholder_id)}" ${item.stakeholder_id === s.stakeholder_id ? "selected" : ""}>${esc(s.stakeholder_id)} · ${esc(s.name)}</option>`).join("")}</select></label>`
      + `<div class="row">${inp("name", "Name", "leave empty if the PRD gives none")}${inp("role", "Role")}</div>`
      + PERSONA_FIELDS.map(([f, label]) => ta(f, label)).join("");
  }
  if (coll === "goals") {
    const benefits = list("benefits");
    return ta("statement", "Statement", "what is sought, with any target", 3)
      + ta("source", "PRD source", "exact PRD words; leave empty if none", 2)
      + `<label>Type<select class="input" name="goal_type">${[["", "Unclear"], ["hard", "Hard: checkable condition"], ["soft", "Soft: quality to satisfice"]].map(([o, l]) => `<option value="${o}" ${(item.goal_type || "") === o ? "selected" : ""}>${l}</option>`).join("")}</select></label>`
      + `<label>Delivers benefits<div class="checks">${benefits.length ? benefits.map((b) => `<label title="${esc(unflag(b.description))}"><input type="checkbox" name="benefit_ids" value="${esc(b.id)}" ${(item.benefit_ids || []).includes(b.id) ? "checked" : ""}>${esc(b.id)}</label>`).join("") : '<span class="faint">No benefits yet</span>'}</div></label>`
      + `<div class="form-group"><span class="flabel">Actors</span><div class="actors-edit">${(item.actors || []).map(actorRow).join("")}</div>
          <button type="button" class="btn" data-act="add-actor">+ Add actor</button></div>`
      + ta("resources", "Resources", "one per line") + ta("plans", "Plans", "how actors pursue it") + ta("justification", "Justification", "why it matters");
  }
  let html = ta("description", "Description", "", 3) + ta("source", "PRD source", "exact PRD words; leave empty if none", 2);
  if (coll === "benefits") {
    html += inp("measure", "Measure", "a target makes it a hard benefit");
    const problems = list("problems");
    html += `<label>Addresses<div class="checks">${problems.length ? problems.map((p) => `<label title="${esc(unflag(p.description))}"><input type="checkbox" name="addresses" value="${esc(p.id)}" ${(item.addresses || []).includes(p.id) ? "checked" : ""}>${esc(p.id)}</label>`).join("") : '<span class="faint">No problems yet</span>'}</div></label>`;
  }
  return html;
}

function editCard(coll, item, key) {
  const isNew = key.startsWith("new:");
  return `<div class="item editing" id="card-${esc(key)}">
    <div class="item-head"><span class="iid">${isNew ? "New " + COLL_LABEL[coll] : esc(idOf(coll, item))}</span>${isNew ? "" : statusPill(key)}</div>
    <form class="form" data-form="${esc(key)}" data-coll="${coll}">${formFields(coll, item)}
      ${S.formError ? `<div class="form-err">${esc(S.formError)}</div>` : ""}
      <div class="actions"><button class="btn primary" type="submit">${isNew ? "Add" : "Save"}</button>
      <button class="btn" type="button" data-act="cancel-edit">Cancel</button>
</div></form></div>`;
}

function collectionSection({ coll, title, code, lede }) {
  const items = list(coll);
  const proposed = items.filter((i) => meta(`${coll}:${idOf(coll, i)}`)?.status === "proposed").length;
  const deleted = S.session?.deleted?.[coll] || [];
  const adding = S.editing === `new:${coll}`;
  const blank = coll === "benefits" ? { addresses: [] } : {};
  return `<div class="section" id="sec-${coll}">
    <div class="section-head"><h2>${esc(title)}</h2>${code ? `<span class="code-tag">${code}</span>` : ""}
      <span class="badge">${items.length}</span>${proposed ? `<span class="badge warn">${proposed} to review</span>` : ""}
      <span class="grow"></span>
      ${proposed ? `<button class="btn ok" data-act="accept-all" data-coll="${coll}" ${dis()}>Accept all proposed</button>` : ""}
      <button class="btn" data-act="add" data-coll="${coll}" ${dis()}>+ Add ${COLL_LABEL[coll]}</button></div>
    ${lede ? `<p class="small muted" style="margin:-4px 0 10px">${esc(lede)}</p>` : ""}
    <div class="list">${adding ? editCard(coll, blank, `new:${coll}`) : ""}
      ${items.length ? items.map((i) => itemCard(coll, i)).join("") : adding ? "" : `<div class="empty">No ${COLL_LABEL[coll]}s ${stageStatus(S.config.collections[coll].stage) === "done" ? "were found in the PRD" : "yet"}.</div>`}</div>
    ${deleted.length ? `<button class="btn ghost small" data-act="toggle-deleted" data-coll="${coll}" style="margin-top:6px" aria-expanded="${S.showDeleted.has(coll)}">${S.showDeleted.has(coll) ? "Hide" : "Show"} deleted (${deleted.length})</button>
      ${S.showDeleted.has(coll) ? `<div class="list" style="margin-top:6px">${deleted.map((d) => {
        const id = idOf(coll, d.item);
        const label = textOf(d.item) ? unflag(textOf(d.item)) : d.item.name || d.item.role || "";
        return `<div class="item deleted"><div class="item-head"><span class="iid">${esc(id)}</span><span class="pill bad">Deleted ${esc(dateTime(d.at))}</span><span class="grow"></span>
          <button class="btn" data-act="restore" data-coll="${coll}" data-id="${esc(id)}" ${dis()}>Restore</button></div><div class="item-text">${esc(label)}</div></div>`;
      }).join("")}</div>` : ""}` : ""}
  </div>`;
}

/* ---------- pages ---------- */
const PAGE_RENDER = {
  welcome() {
    const sessions = S.sessions.length ? `<div class="card"><div class="card-head"><h2>Recent sessions</h2></div>
      ${S.sessions.slice(0, 8).map((x) => `<button class="sess" data-act="open-session" data-sid="${esc(x.id)}">
        <span>${esc(x.title)} <span class="mono faint">${esc(x.id)}</span>${S.session?.id === x.id ? ' <span class="pill info">open</span>' : ""}</span>
<span class="small faint">${esc(dateTime(x.updated_at))}</span></button>`).join("")}</div>` : "";

    if (S.session && !S.composing) {
      const s = S.session;
      const nodeEvents = s.events.filter((e) => ["node", "run", "error"].includes(e.kind)).slice(-14).reverse();
      return `<h1>Welcome <span class="code-tag">session ${esc(s.id)}</span></h1>
        <p class="lede">The flow ran on this PRD. Each page holds one part of the result, and every artifact keeps the PRD quote it came from.</p>
        <div class="card"><div class="card-head"><h2>Pipeline</h2><span class="grow"></span>
          <button class="btn" data-act="new-session" ${dis()}>New PRD</button>
          ${running() ? "" : '<button class="btn primary" data-act="nav" data-page="intent">Review capture intent →</button>'}</div>
          ${flowStrip()}
          <h3 style="margin-top:16px">Run log</h3>
          <ul class="timeline">${nodeEvents.map(eventRow).join("") || '<li class="faint">Starting…</li>'}</ul></div>
        <div class="card"><div class="card-head"><h2>PRD</h2><span class="pill neutral">${s.state.prd.length.toLocaleString()} chars</span></div><pre class="prd">${esc(s.state.prd)}</pre></div>
        ${sessions}`;
    }
    return `<h1>Welcome to IDE3.0</h1>
      <p class="lede">Paste a product requirements document. IDE3.0 extracts the intent (SSON, problems, benefits, effects, invariants, constraints, exclusions) models the users (stakeholders, personas), extracts their goals and builds a use case model. Each result keeps the PRD quote it came from, so you can review, edit and trace it.</p>
      <div class="card"><div class="card-head"><h2>Product requirements document</h2><span class="grow"></span>
        <span class="small faint">${S.prd.length.toLocaleString()} chars</span></div>
        <textarea class="input prd-input" id="prdInput" placeholder="Paste the PRD here…" aria-label="PRD text">${esc(S.prd)}</textarea>
        <div class="actions" style="margin-top:14px"><button class="btn primary big" data-act="run" ${S.prd.trim() ? "" : "disabled"}>Run the flow</button>
          ${S.session ? '<button class="btn" data-act="cancel-compose">Back to current session</button>' : ""}
          <span class="small faint">Runs on <span class="mono">${esc(S.config.model)}</span>, 9 model calls; this can take a few minutes.</span></div>
        <div style="margin-top:14px">${flowStrip(true)}</div></div>
      ${sessions}`;
  },

  intent() {
    const ci = intent();
    const banners = stageBanners(["sson", "sson_eval"]);
    if (!ci.single_statement_intent) return `<h1>Capture intent <span class="code-tag">G.1</span></h1>${banners}${noRun("this page will")}`;
    const key = "singleton:sson";
    const editing = S.editing === key;
    const ev = ci.sson_evaluation;
    const evalStale = ["stale", "running", "queued"].includes(stageStatus("sson_eval"));
    const field = (label, v) => `<div class="field"><span class="kind">${label}</span><div class="v ${v ? "" : "none"}">${esc(v || "Not in the PRD")}</div></div>`;
    const sson = editing ? `<form class="form" data-form="${key}">
        <label>Single statement of need<textarea class="input" name="single_statement_intent" rows="4">${esc(unflag(ci.single_statement_intent))}</textarea></label>
        <div class="row"><label>What<input class="input" name="what" value="${esc(ci.what || "")}"></label><label>How<input class="input" name="how" value="${esc(ci.how || "")}"></label></div>
        <div class="row"><label>Why<input class="input" name="why" value="${esc(ci.why || "")}"></label><label>Success measure<input class="input" name="success_measure" value="${esc(ci.success_measure || "")}"></label></div>
        <label>Context and overall objective (G.1)<textarea class="input" name="context_and_objective" rows="3">${esc(ci.context_and_objective || "")}</textarea></label>
        ${S.formError ? `<div class="form-err">${esc(S.formError)}</div>` : ""}
        <div class="actions"><button class="btn primary" type="submit">Save</button><button class="btn" type="button" data-act="cancel-edit">Cancel</button>
        <span class="small faint">Saving marks the evaluation, situation and user modelling as out of date.</span></div></form>`
      : `<div class="intent-box">${esc(unflag(ci.single_statement_intent))}</div>
        <div class="fields">${field("What", ci.what)}${field("How", ci.how)}${field("Why", ci.why)}${field("Success measure", ci.success_measure)}</div>
        <div class="field" style="margin-top:12px"><span class="kind">G.1 Context and overall objective</span><div class="v">${esc(ci.context_and_objective || "")}</div></div>`;
    const status = meta(key)?.status;
    return `<h1>Capture intent <span class="code-tag">G.1 · SSON</span></h1>
      <p class="lede">The single statement of need (SSON) that the other artifacts are checked against. A 🚩 means the model wrote it because the PRD has no sentence that works as one.</p>
      ${banners}
      <div class="card item st-${status || "proposed"}" id="card-${key}" style="padding:14px 16px">
        <div class="card-head"><h2>Single statement of need</h2>${statusPill(key)}
          <span class="pill ${ci.sson_source === "stated" ? "ok" : "neutral"}">${ci.sson_source === "stated" ? "Stated in PRD" : "Synthesized"}</span>${flagPill(ci.single_statement_intent)}
          <span class="grow"></span>${editing ? "" : `<span class="actions">
          ${status && status !== "accepted" ? `<button class="btn ok" data-act="accept" data-coll="${key}" ${dis()}>Accept</button>` : ""}
          <button class="btn" data-act="edit" data-key="${key}" ${dis()}>Edit</button></span>`}</div>
        ${sson}</div>
      <div class="row">
        <div class="card ${evalStale ? "dim" : ""}" style="flex:1.4"><div class="card-head"><h2>SSON evaluation</h2><span class="code-tag">L04 criteria</span><span class="grow"></span>
          <button class="btn" data-act="rerun" data-stage="sson_eval" ${dis()}>Re-evaluate</button></div>
          ${ev ? `<div class="card-head"><div class="score"><b>${ev.score}</b><span class="faint">/100</span></div><span class="pill ${ev.passed ? "ok" : "warn"}">${ev.passed ? "Passes" : "Needs work"}</span><span class="small faint">Non-blocking: reported only</span></div>
          <table><thead><tr><th>Criterion</th><th>Verdict</th><th>Reason</th></tr></thead><tbody>
          ${Object.entries(ev.criteria).map(([k, c]) => `<tr><td>${esc(CRITERIA[k] || k)}</td><td><span class="pill ${c.verdict === "met" ? "ok" : c.verdict === "partially_met" ? "warn" : "bad"}">${esc(c.verdict.replace("_", " "))}</span></td><td class="muted">${esc(c.reason)}</td></tr>`).join("")}
          </tbody></table><div class="quote" style="margin-top:12px"><span class="kind">Feedback</span>${esc(ev.feedback)}</div>` : '<div class="empty">Not evaluated yet.</div>'}</div>
        <div class="card"><div class="card-head"><h2>Evidence from the PRD</h2><span class="badge">${(ci.sson_evidence || []).length}</span></div>
          ${(ci.sson_evidence || []).map((q) => `<div class="quote">“${esc(q)}”</div>`).join("") || '<div class="empty">No PRD sentence supports the SSON.</div>'}
          <div class="actions" style="margin-top:14px"><button class="btn warn" data-act="rerun" data-stage="sson" data-cascade="1" ${dis()}>Re-extract from PRD…</button></div></div>
      </div>`;
  },

  situation() {
    const ci = intent();
    const banners = stageBanners(["context"]);
    if (!S.session || (!ci.current_situation && !ci.problems)) return `<h1>Situation & benefits <span class="code-tag">G.2 · G.3 · E.5 · E.6</span></h1>${banners}${noRun("this page will")}`;
    const key = "singleton:situation";
    const editing = S.editing === key;
    return `<h1>Situation & benefits <span class="code-tag">G.2 · G.3 · E.5 · E.6</span></h1>
      <p class="lede">What happens today, what goes wrong, what improves, and what the environment imposes. Accept, edit, add or delete items. Each one keeps the PRD quote it came from.</p>
      ${banners}
      <div class="subnav">${CONTEXT_SECTIONS.map((s) => `<button class="btn" data-act="scroll" data-target="sec-${s.coll}">${esc(s.title)} <span class="faint">${list(s.coll).length}</span></button>`).join("")}</div>
      <div class="card item st-${meta(key)?.status || "proposed"}" id="card-${key}"><div class="card-head"><h2>Current situation</h2><span class="code-tag">G.2</span>${statusPill(key)}<span class="grow"></span>
        ${editing ? "" : `<span class="actions">${meta(key) && meta(key).status !== "accepted" ? `<button class="btn ok" data-act="accept" data-coll="${key}" ${dis()}>Accept</button>` : ""}
        <button class="btn" data-act="edit" data-key="${key}" ${dis()}>Edit</button></span>`}</div>
        ${editing ? `<form class="form" data-form="${key}"><textarea class="input" name="current_situation" rows="4" aria-label="Current situation">${esc(ci.current_situation || "")}</textarea>
          ${S.formError ? `<div class="form-err">${esc(S.formError)}</div>` : ""}
          <div class="actions"><button class="btn primary" type="submit">Save</button><button class="btn" type="button" data-act="cancel-edit">Cancel</button></div></form>`
        : `<div>${esc(ci.current_situation || "") || '<span class="faint">The PRD does not describe the current situation.</span>'}</div>`}</div>
      ${CONTEXT_SECTIONS.map(collectionSection).join("")}`;
  },

  stakeholders() {
    const banners = stageBanners(["stakeholders"]);
    if (!S.session || !st().stakeholder_metadata) return `<h1>Stakeholders</h1>${banners}${noRun("stakeholders will")}`;
    return `<h1>Stakeholders <span class="code-tag">user modelling</span></h1>
      <p class="lede">Everyone affected by the system. Direct stakeholders use it and should be represented by a persona. Indirect ones are affected without using it.</p>
      ${banners}${collectionSection({ coll: "stakeholders", title: "Stakeholders" })}`;
  },

  personas() {
    const banners = stageBanners(["personas"]);
    if (!S.session || !st().persona_metadata) return `<h1>Personas</h1>${banners}${noRun("personas will")}`;
    return `<h1>Personas <span class="code-tag">MSF template</span></h1>
      <p class="lede">Representative users, each linked to the stakeholder group it stands for. Fields the PRD does not support stay empty instead of being invented.</p>
      ${banners}${collectionSection({ coll: "personas", title: "Personas" })}`;
  },

  goals() {
    const banners = stageBanners(["goals"]);
    if (!S.session || !st().goal_metadata) return `<h1>Goals</h1>${banners}${noRun("goals will")}`;
    return `<h1>Goals <span class="code-tag">hard · soft</span></h1>
      <p class="lede">What stakeholders want to achieve. Hard goals have a checkable condition; soft goals are qualities to satisfice. Each goal links to the benefits that show it is reached and to the stakeholders who act on it.</p>
      ${banners}${collectionSection({ coll: "goals", title: "Goals" })}`;
  },

  usecases() {
    const banners = stageBanners(["use_cases"]);
    const m = st().use_case_metadata;
    if (!S.session || !m || !m.system_name) return `<h1>Use cases</h1>${banners}${noRun("the use case model will")}`;
    const actors = new Map(m.actors.map((a) => [a.actor_id, a]));
    const cases = new Map(m.use_cases.map((c) => [c.use_case_id, c]));
    const holders = new Set(list("stakeholders").map((x) => x.stakeholder_id));
    const goalIds = new Set(list("goals").map((g) => g.goal_id));
    const actorChip = (id) => { const a = actors.get(id); return a ? `<span class="pill neutral" title="${esc(id)}">${esc(a.name)}</span>` : `<span class="chip dangling">${esc(id)}</span>`; };
    const caseChip = (id) => `<button class="chip" data-act="jump" data-key="usecases:${esc(id)}">${esc(id)}</button> <span class="small muted">${esc(cases.get(id)?.name || "")}</span>`;
    const caseCards = m.use_cases.map((c) => {
      const inc = m.relationships.filter((r) => r.source === c.use_case_id && r.kind === "include");
      const ext = m.relationships.filter((r) => r.source === c.use_case_id && r.kind === "extend");
      const by = m.relationships.filter((r) => r.target === c.use_case_id);
      return `<div class="item st-proposed" id="card-usecases:${esc(c.use_case_id)}">
        <div class="item-head"><span class="iid">${esc(c.use_case_id)}</span><span class="item-title">${esc(c.name)}</span></div>
        ${c.description ? `<div class="item-text">${esc(c.description)}</div>` : ""}
        <div class="links"><span class="kind">Primary actor</span>${c.primary_actor_id ? actorChip(c.primary_actor_id) : '<span class="pill warn">none</span>'}
          ${(c.supporting_actor_ids || []).length ? `<span class="kind">Supporting</span>${c.supporting_actor_ids.map(actorChip).join("")}` : ""}</div>
        <div class="links"><span class="kind">Achieves</span>${(c.goal_ids || []).length ? c.goal_ids.map((g) => goalIds.has(g) ? `<button class="chip" data-act="jump" data-key="goals:${esc(g)}">${esc(g)}</button>` : `<span class="chip dangling">${esc(g)}</span>`).join("") : '<span class="pill warn">no goal</span>'}</div>
        ${inc.length ? `<div class="links"><span class="kind">«include»</span>${inc.map((r) => caseChip(r.target)).join("")}</div>` : ""}
        ${ext.length ? `<div class="links"><span class="kind">«extend»</span>${ext.map((r) => `${caseChip(r.target)} <span class="small faint">${esc(r.condition || "no condition")}</span>`).join("")}</div>` : ""}
        ${by.length ? `<div class="links"><span class="kind">Used by</span>${by.map((r) => `${caseChip(r.source)} <span class="small faint">${r.kind === "include" ? "«include»" : "«extend»"}</span>`).join("")}</div>` : ""}
      </div>`;
    }).join("");
    const actorRows = m.actors.map((a) => {
      const primary = m.use_cases.filter((c) => c.primary_actor_id === a.actor_id).map((c) => c.use_case_id);
      const support = m.use_cases.filter((c) => (c.supporting_actor_ids || []).includes(a.actor_id)).map((c) => c.use_case_id);
      const chips = (ids) => ids.map((id) => `<button class="chip" data-act="jump" data-key="usecases:${esc(id)}">${esc(id)}</button>`).join(" ") || '<span class="faint">—</span>';
      return `<tr><td class="mono">${esc(a.actor_id)}</td><td>${esc(a.name)}</td><td><span class="pill neutral">${esc(a.kind)}</span></td>
        <td>${a.stakeholder_id ? (holders.has(a.stakeholder_id) ? `<button class="chip" data-act="jump" data-key="stakeholders:${esc(a.stakeholder_id)}">${esc(a.stakeholder_id)}</button>` : `<span class="chip dangling">${esc(a.stakeholder_id)}</span>`) : '<span class="faint">not a stakeholder</span>'}</td>
        <td>${chips(primary)}</td><td>${chips(support)}</td></tr>`;
    }).join("");
    return `<h1>Use cases <span class="code-tag">L13 · rough model</span></h1>
      <p class="lede">What each actor achieves with the system, drawn as a UML use case diagram. Built from the goals, stakeholders and PRD. Each use case links to the goals it achieves. This is read-only for now; re-run the stage to rebuild it.</p>
      ${banners}
      <div class="card ucd-wrap">${useCaseDiagram(m)}</div>
      ${useCaseLegend()}
      <div class="card"><div class="card-head"><h2>Model checks</h2><span class="badge ${m.issues.length ? "warn" : "ok"}">${m.issues.length}</span><span class="small faint">From the L13 pitfalls; reported, not fixed.</span></div>
        ${m.issues.length ? `<ul class="checks-list">${m.issues.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>` : '<div class="empty">No problems found.</div>'}</div>
      <div class="section"><div class="section-head"><h2>Use cases</h2><span class="badge">${m.use_cases.length}</span></div><div class="list">${caseCards}</div></div>
      <div class="section"><div class="section-head"><h2>Actors</h2><span class="badge">${m.actors.length}</span></div>
        <div class="card" style="padding:4px 8px"><table><thead><tr><th>ID</th><th>Actor</th><th>Kind</th><th>Stakeholder</th><th>Primary in</th><th>Supports</th></tr></thead><tbody>${actorRows}</tbody></table></div></div>`;
  },

  trace() {
    const g = st().artifact_graph;
    if (!g) return `<h1>Trace</h1>${noRun("the trace will")}`;
    const cov = coverage();
    return `<h1>Trace <span class="code-tag">artifact graph</span></h1>
      <p class="lede">How every artifact connects back to the intent and to the PRD. It is rebuilt after every edit, so gaps show up as soon as they appear.</p>
      <div class="stats">
        <div class="stat"><span class="kind">Artifacts</span><b>${g.nodes.length}</b></div>
        <div class="stat"><span class="kind">Trace links</span><b>${g.edges.length}</b></div>
        <div class="stat"><span class="kind">Gaps</span><b style="color:${g.gaps.length ? "var(--bad)" : "var(--ok)"}">${g.gaps.length}</b></div>
        <div class="stat"><span class="kind">PRD covered</span><b>${cov.percent}%</b></div>
      </div>
      <div class="seg" role="tablist">${[["graph", "Graph"], ["impact", `Impact${pendingChanges().length ? ` · ${pendingChanges().length}` : ""}`], ["prd", "PRD coverage"], ["log", "Activity"]].map(([id, l]) => `<button role="tab" aria-selected="${S.traceTab === id}" class="${S.traceTab === id ? "on" : ""}" data-act="trace-tab" data-tab="${id}">${l}</button>`).join("")}</div>
      ${S.traceTab === "graph" ? traceGraph(g) : S.traceTab === "impact" ? traceImpact() : S.traceTab === "prd" ? tracePrd(cov) : traceLog()}`;
  },
};

function flowStrip(preview = false) {
  const stages = S.config.stages;
  return `<div class="flow">${stages.map((s, i) => {
    const status = preview || !S.session ? "" : stageStatus(s.id);
    const icon = status === "running" ? '<span class="spinner" style="width:10px;height:10px"></span>' : status === "done" ? '<span style="color:var(--ok)">✓</span>' : status === "stale" ? '<span style="color:var(--warn)">↻</span>' : status === "error" ? '<span style="color:var(--bad)">!</span>' : "";
    return `${i ? '<span class="arrow">→</span>' : ""}<span class="stage ${status}">${icon}${esc(s.label)}</span>`;
  }).join("")}</div>`;
}

function eventRow(e) {
  const cls = { run: "info", node: "neutral", edit: "warn", review: "ok", stale: "warn", error: "bad" }[e.kind] || "neutral";
  const ref = e.ref ? ` <button class="chip" data-act="jump" data-key="${esc(e.ref)}">${esc(e.ref.split(":")[1])}</button>` : "";
  return `<li><span class="when">${esc(time(e.at))}</span><span><span class="pill ${cls}">${esc(e.kind)}</span></span><span>${esc(e.detail)}${ref}</span><span class="ms">${e.ms !== undefined ? (e.ms / 1000).toFixed(1) + "s" : ""}</span></li>`;
}

/* ---------- use case model (3RA3 L13 notation) ---------- */
function wrapText(text, max) {
  const lines = [];
  let line = "";
  for (const word of String(text || "").split(/\s+/).filter(Boolean)) {
    if (line && (line + " " + word).length > max) { lines.push(line); line = word; }
    else line = line ? line + " " + word : word;
  }
  if (line) lines.push(line);
  return lines;
}
function svgLines(lines, x, y, lineHeight, cls) {
  // a block of centred lines whose middle sits at y
  const top = y - ((lines.length - 1) * lineHeight) / 2;
  return `<text class="${cls}" x="${x}" y="${top}" text-anchor="middle" dominant-baseline="middle">${lines.map((l, i) => `<tspan x="${x}" dy="${i ? lineHeight : 0}">${esc(l)}</tspan>`).join("")}</text>`;
}
function stickFigure(x, y, cls = "uc-figure") {
  return `<g class="${cls}"><circle cx="${x}" cy="${y - 30}" r="9"/><path d="M${x} ${y - 21}V${y + 6}M${x - 15} ${y - 12}H${x + 15}M${x} ${y + 6}L${x - 12} ${y + 27}M${x} ${y + 6}L${x + 12} ${y + 27}"/></g>`;
}

function useCaseDiagram(m) {
  const cases = m.use_cases || [], actors = m.actors || [], rels = m.relationships || [];
  if (!cases.length) return '<div class="empty">No use cases were modelled.</div>';
  const RX = 126, GAP = 34, LH = 15, PAD = 40, TITLE = 58, SIDE = 160, ACTOR_H = 150, MARGIN = 80;

  // primary actors on the left; actors that only support go on the right (L13 convention)
  const primaryIds = new Set(cases.map((c) => c.primary_actor_id).filter(Boolean));
  const left = actors.filter((a) => primaryIds.has(a.actor_id));
  const right = actors.filter((a) => !primaryIds.has(a.actor_id));
  const rank = new Map(left.map((a, i) => [a.actor_id, i]));
  const ordered = [...cases].sort((a, b) => (rank.get(a.primary_actor_id) ?? 99) - (rank.get(b.primary_actor_id) ?? 99));

  const twoCols = ordered.length > 7;
  const perCol = twoCols ? Math.ceil(ordered.length / 2) : ordered.length;
  const bx = SIDE + MARGIN;
  // room on the right of the column for «include»/«extend» arcs and their labels
  const arcRoom = !rels.length ? 40 : rels.some((r) => r.kind === "extend" && r.condition) ? 250 : 160;
  const colX = [bx + PAD + RX];
  if (twoCols) colX.push(colX[0] + 2 * RX + 80);
  const bw = colX.at(-1) + RX + arcRoom - bx;
  const pos = {};
  const colH = [TITLE, TITLE];
  ordered.forEach((c, i) => {
    const col = twoCols && i >= perCol ? 1 : 0;
    const lines = wrapText(c.name, 24);
    const ry = Math.max(30, (lines.length * LH) / 2 + 16);
    pos[c.use_case_id] = { cx: colX[col], cy: colH[col] + ry, ry, lines, col };
    colH[col] += 2 * ry + GAP;
  });
  const bh = Math.max(Math.max(...colH) - GAP + PAD, left.length * ACTOR_H + 20, right.length * ACTOR_H + 20);
  const width = bx + bw + MARGIN + SIDE, height = bh + 30;

  // each actor sits level with the use cases it takes part in, without overlapping
  const links = (aid) => cases.filter((c) => c.primary_actor_id === aid || (c.supporting_actor_ids || []).includes(aid));
  const actorPos = {};
  const place = (list, x) => {
    const wanted = list.map((a) => {
      const ys = links(a.actor_id).map((c) => pos[c.use_case_id].cy);
      return { a, y: ys.length ? ys.reduce((s, v) => s + v, 0) / ys.length : bh / 2 };
    }).sort((p, q) => p.y - q.y);
    let prev = -Infinity;
    for (const p of wanted) { p.y = Math.max(p.y, 60, prev + ACTOR_H); prev = p.y; }
    const overflow = prev - (bh - 70);
    if (overflow > 0) wanted.forEach((p) => (p.y -= overflow));
    wanted.forEach((p) => (actorPos[p.a.actor_id] = { x, y: Math.max(p.y, 52), side: x < bx ? "left" : "right" }));
  };
  place(left, SIDE / 2);
  place(right, bx + bw + MARGIN + SIDE / 2);

  const edge = (p, tx, ty) => {
    const dx = tx - p.cx, dy = ty - p.cy;
    const t = 1 / Math.sqrt((dx * dx) / (RX * RX) + (dy * dy) / (p.ry * p.ry));
    return [p.cx + dx * t, p.cy + dy * t];
  };

  const assoc = [];
  for (const c of cases) {
    for (const aid of [c.primary_actor_id, ...(c.supporting_actor_ids || [])].filter(Boolean)) {
      const a = actorPos[aid];
      if (!a) continue;
      const ax = a.x + (a.side === "left" ? 18 : -18), ay = a.y - 8;
      const [ex, ey] = edge(pos[c.use_case_id], ax, ay);
      assoc.push(`<line class="uc-assoc" data-uc="${esc(c.use_case_id)}" data-actor="${esc(aid)}" x1="${ax}" y1="${ay}" x2="${ex}" y2="${ey}"/>`);
    }
  }

  const relSvg = [];
  const bulges = {};
  for (const r of rels) {
    const s = pos[r.source], t = pos[r.target];
    if (!s || !t) continue;
    const label = r.kind === "include" ? "«include»" : "«extend»";
    let path, lx, ly, anchor = "middle";
    if (s.col === t.col) {
      const k = (bulges[s.col] = (bulges[s.col] || 0) + 1);
      const bulge = 58 + 26 * (k - 1);
      const [sx, sy] = edge(s, s.cx + 4 * RX, s.cy + (t.cy > s.cy ? 1 : -1) * s.ry * 2);
      const [tx, ty] = edge(t, t.cx + 4 * RX, t.cy + (s.cy > t.cy ? 1 : -1) * t.ry * 2);
      const mx = Math.max(sx, tx) + bulge;
      path = `M${sx},${sy} C${mx},${sy} ${mx},${ty} ${tx},${ty}`;
      // the label sits just right of the arc's outermost point
      lx = mx - bulge * 0.25 + 8; ly = (sy + ty) / 2 - 2; anchor = "start";
    } else {
      const [sx, sy] = edge(s, t.cx, t.cy), [tx, ty] = edge(t, s.cx, s.cy);
      path = `M${sx},${sy} L${tx},${ty}`;
      lx = (sx + tx) / 2; ly = (sy + ty) / 2 - 8;
    }
    const cond = r.kind === "extend" && r.condition ? `<tspan x="${lx}" dy="13" class="uc-cond">[${esc(r.condition.length > 30 ? r.condition.slice(0, 29) + "…" : r.condition)}]</tspan>` : "";
    relSvg.push(`<g class="uc-rel" data-uc="${esc(r.source)} ${esc(r.target)}"><path d="${path}" marker-end="url(#uc-open)"/>
      <text x="${lx}" y="${ly}" text-anchor="${anchor}" class="uc-rel-label"><tspan x="${lx}">${label}</tspan>${cond}</text></g>`);
  }

  const ellipses = ordered.map((c) => {
    const p = pos[c.use_case_id];
    return `<g class="uc-node" data-uc-node="${esc(c.use_case_id)}" data-act="jump" data-key="usecases:${esc(c.use_case_id)}" tabindex="0" role="button" aria-label="${esc(c.use_case_id)} ${esc(c.name)}">
      <title>${esc(c.use_case_id)}: ${esc(c.description || c.name)}</title>
      <ellipse cx="${p.cx}" cy="${p.cy}" rx="${RX}" ry="${p.ry}"/>${svgLines(p.lines, p.cx, p.cy, LH, "uc-name")}</g>`;
  }).join("");

  const figures = actors.filter((a) => actorPos[a.actor_id]).map((a) => {
    const p = actorPos[a.actor_id];
    const lines = wrapText(a.name, 20).slice(0, 3);
    const stereo = a.kind !== "human" ? `<text class="uc-stereo" x="${p.x}" y="${p.y + 47 + lines.length * 13}" text-anchor="middle">«${esc(a.kind)}»</text>` : "";
    return `<g class="uc-actor" data-uc-actor="${esc(a.actor_id)}"><title>${esc(a.actor_id)}: ${esc(a.name)}</title>${stickFigure(p.x, p.y)}
      ${svgLines(lines, p.x, p.y + 44 + ((lines.length - 1) * 13) / 2, 13, "uc-actor-name")}${stereo}</g>`;
  }).join("");

  return `<svg class="ucd" id="ucd" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="Use case diagram: ${esc(m.system_name)}">
    <defs><marker id="uc-open" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse"><path d="M1,1 L9,5 L1,9" class="uc-arrowhead"/></marker></defs>
    <rect class="uc-boundary" x="${bx}" y="8" width="${bw}" height="${bh}" rx="6"/>
    <text class="uc-title" x="${bx + 14}" y="30">${esc(m.system_name || "System")}</text>
    ${assoc.join("")}${relSvg.join("")}${ellipses}${figures}</svg>`;
}

function useCaseLegend() {
  const sample = (inner, w = 64, h = 34) => `<svg class="ucd legend-svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><defs><marker id="uc-open-l" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse"><path d="M1,1 L9,5 L1,9" class="uc-arrowhead"/></marker></defs>${inner}</svg>`;
  const rows = [
    [sample(stickFigure(32, 42), 64, 72), "<b>Actor</b>: a person, system or organization outside the system. Primary actors (whose goal the use case meets) on the left; actors that only support on the right. Non-human actors are marked «system» or «organization»."],
    [sample('<ellipse cx="32" cy="17" rx="30" ry="13" class="uc-legend-ellipse"/>'), "<b>Use case</b>: something an actor achieves with the system, named with a verb (\"Book pickup slot\"). Click one to open its details."],
    [sample('<rect x="3" y="4" width="58" height="26" rx="4" class="uc-boundary"/>'), "<b>System boundary</b>: use cases are inside it; actors are never inside it."],
    [sample('<line x1="4" y1="17" x2="60" y2="17" class="uc-assoc"/>'), "<b>Association</b> (solid line): the actor takes part in the use case."],
    [sample('<g class="uc-rel"><path d="M4,22 L58,22" marker-end="url(#uc-open-l)"/><text x="31" y="13" text-anchor="middle" class="uc-rel-label">«include»</text></g>'), "<b>«include»</b> (dashed, open arrow): the base use case always uses the included one. The arrow points from the base to the included use case."],
    [sample('<g class="uc-rel"><path d="M4,22 L58,22" marker-end="url(#uc-open-l)"/><text x="31" y="13" text-anchor="middle" class="uc-rel-label">«extend»</text></g>'), "<b>«extend» [condition]</b> (dashed, open arrow): the extension may add to the base under the condition. The arrow points from the extension to the base."],
  ];
  return `<div class="card"><h3>Legend · 3RA3 L13 notation</h3><div class="uc-legend">${rows.map(([svg, text]) => `<div class="legend-row">${svg}<span>${text}</span></div>`).join("")}</div></div>`;
}

function focusUseCase(id) {
  const svg = $("#ucd");
  if (!svg) return;
  svg.classList.toggle("focus", !!id);
  svg.querySelectorAll("[data-uc-node]").forEach((n) => n.classList.toggle("hot", n.dataset.ucNode === id));
  const actorIds = new Set();
  svg.querySelectorAll(".uc-assoc").forEach((l) => {
    const hot = l.dataset.uc === id;
    l.classList.toggle("hot", hot);
    if (hot) actorIds.add(l.dataset.actor);
  });
  svg.querySelectorAll("[data-uc-actor]").forEach((a) => a.classList.toggle("hot", actorIds.has(a.dataset.ucActor)));
  svg.querySelectorAll(".uc-rel").forEach((r) => r.classList.toggle("hot", !!id && r.dataset.uc.split(" ").includes(id)));
}

/* ---------- trace: graph ---------- */
// Left to right: who (personas, stakeholders), the need, then what it breaks into.
const GRAPH_COLS = [["persona", "Personas"], ["stakeholder", "Stakeholders"], ["intent", "Intent"], ["goal", "Goals"], ["use_case", "Use cases"], ["benefit", "Benefits"], ["problem", "Problems"]];
const TYPE_COLOR = { persona: "#b294f0", stakeholder: "#4fb6b0", intent: "#5b9cf5", goal: "#e68ac0", use_case: "#e8a15c", benefit: "#4fb67d", problem: "#e3625f" };
const TYPE_NAME = { persona: "Persona", stakeholder: "Stakeholder", intent: "Intent (SSON)", goal: "Goal", use_case: "Use case", benefit: "Benefit", problem: "Problem" };
const TYPE_DEF = {
  persona: "A representative user (MSF template) standing in for a stakeholder group.",
  stakeholder: "Anyone who brings value to the project or is affected by it, directly or indirectly.",
  intent: "The single statement of need (SSON): what the system is for and how success is judged (G.1).",
  goal: "What stakeholders want to achieve. Hard goals are checkable; soft goals are qualities.",
  use_case: "Something an actor achieves with the system (L13 use case model).",
  benefit: "An expected improvement (G.3). Hard benefits carry a measure from the PRD.",
  problem: "Something that goes wrong today (G.2 current situation).",
};
// Each link points from an artifact to the one it traces up to.
const RELATIONS = {
  represents: { from: "persona", to: "stakeholder", verb: "represents", def: "The persona stands in for that stakeholder group." },
  concerned_with: { from: "stakeholder", to: "intent", verb: "is concerned with", def: "The stakeholder has a stake in the need." },
  refines: { from: "goal", to: "intent", verb: "refines", def: "The goal is a concrete objective under the need." },
  involves: { from: "goal", to: "stakeholder", verb: "involves", def: "The stakeholder acts in or wants the goal (a goal actor)." },
  delivers: { from: "goal", to: "benefit", verb: "delivers", def: "Reaching the goal produces the benefit." },
  achieves: { from: "use_case", to: "goal", verb: "achieves", def: "Using the system this way helps reach the goal." },
  serves: { from: "use_case", to: "stakeholder", verb: "serves", def: "The use case's primary actor is this stakeholder." },
  realizes: { from: "benefit", to: "intent", verb: "realizes", def: "The benefit is part of what meeting the need delivers." },
  addresses: { from: "benefit", to: "problem", verb: "addresses", def: "The benefit fixes (part of) the problem." },
  motivates: { from: "problem", to: "intent", verb: "motivates", def: "Fixing the problem is part of why the system is needed." },
};
const GAP_DEF = {
  missing_artifacts: "A whole artifact type was not extracted.",
  duplicate_id: "Two artifacts share an ID; the second is ignored.",
  dangling_link: "A link points to an artifact that no longer exists.",
  unlinked_persona: "A persona represents no stakeholder.",
  stakeholder_without_persona: "A direct stakeholder has no persona.",
  unaddressed_problem: "No benefit addresses this problem.",
  unlinked_goal: "A goal delivers no benefit and involves no stakeholder.",
  benefit_without_goal: "No goal delivers this benefit.",
  goal_without_use_case: "No use case achieves this goal.",
  use_case_without_goal: "A use case achieves no goal.",
  goal_without_story: "A goal has no user story (Goal2Story).",
};
const TYPE_KEY = { problem: "problems", benefit: "benefits", stakeholder: "stakeholders", persona: "personas", goal: "goals", use_case: "usecases" };
const nodeKey = (n) => (n.type === "intent" ? "singleton:sson" : `${TYPE_KEY[n.type]}:${n.id}`);
const relColor = (rel) => TYPE_COLOR[RELATIONS[rel]?.from] || "#6d6e78";

function neighbourhood(g, id) {
  // everything reachable up or down the trace from one artifact (stops at the intent)
  const near = new Set([id]);
  for (const dir of ["up", "down"]) {
    const queue = [id];
    while (queue.length) {
      const cur = queue.shift();
      for (const e of g.edges) {
        const [a, b] = dir === "up" ? [e.source, e.target] : [e.target, e.source];
        if (a === cur && !near.has(b)) { near.add(b); if (b !== "Intent-1") queue.push(b); }
      }
    }
  }
  return near;
}

function visibleCols() {
  return GRAPH_COLS.filter(([t]) => !S.traceHidden.has(t));
}

function orderColumns(g, cols) {
  // barycentre ordering: each node moves toward the average position of its
  // neighbours in the next columns, which removes most link crossings
  const lists = cols.map(([t]) => g.nodes.filter((n) => n.type === t).map((n) => n.id));
  const colOf = new Map();
  lists.forEach((l, i) => l.forEach((id) => colOf.set(id, i)));
  const nbrs = new Map();
  for (const e of g.edges) {
    if (!colOf.has(e.source) || !colOf.has(e.target)) continue;
    (nbrs.get(e.source) || nbrs.set(e.source, []).get(e.source)).push(e.target);
    (nbrs.get(e.target) || nbrs.set(e.target, []).get(e.target)).push(e.source);
  }
  for (let pass = 0; pass < 6; pass++) {
    const pos = new Map();
    lists.forEach((l) => l.forEach((id, i) => pos.set(id, l.length > 1 ? i / (l.length - 1) : 0.5)));
    lists.forEach((l, ci) => {
      const score = (id) => {
        const all = nbrs.get(id) || [];
        const near = all.filter((o) => Math.abs(colOf.get(o) - ci) === 1);
        const use = near.length ? near : all;
        return use.length ? use.reduce((s, o) => s + pos.get(o), 0) / use.length : pos.get(id);
      };
      const scores = new Map(l.map((id) => [id, score(id)]));
      l.sort((a, b) => scores.get(a) - scores.get(b));
    });
  }
  return lists;
}

function linkSample(rel, width = 46, dash = false) {
  const dashed = dash ? 'stroke-dasharray="4 3"' : "";
  const c = rel ? relColor(rel) : "#9b9ca5";
  return `<svg width="${width}" height="10" aria-hidden="true"><line x1="1" y1="5" x2="${width - 7}" y2="5" stroke="${c}" stroke-width="1.6" ${dashed}/><path d="M${width - 8},1 L${width - 1},5 L${width - 8},9 z" fill="${c}"/></svg>`;
}
const typeWord = (t) => `<b style="color:${TYPE_COLOR[t]}">${TYPE_NAME[t].replace(" (SSON)", "")}</b>`;

function traceGraph(g) {
  const cols = visibleCols();
  const lists = orderColumns(g, cols);
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  const gapIds = new Set(g.gaps.map((x) => x.artifact_id).filter(Boolean));
  const counts = Object.fromEntries(GRAPH_COLS.map(([t]) => [t, g.nodes.filter((n) => n.type === t).length]));
  const filters = `<div class="trace-tools"><span class="kind">Show</span>
    ${GRAPH_COLS.map(([t, label]) => `<button class="type-chip ${S.traceHidden.has(t) ? "off" : ""}" data-act="toggle-type" data-type="${t}" aria-pressed="${!S.traceHidden.has(t)}"><span class="tdot" style="background:${TYPE_COLOR[t]}"></span>${label} <span class="faint">${counts[t]}</span></button>`).join("")}
    <span class="grow"></span>
    <label class="switch"><input type="checkbox" data-act="toggle-long" ${S.traceShowLong ? "checked" : ""}> Show links that skip a column</label></div>`;
  const colHtml = cols.map(([type, label], ci) => `<div class="graph-col ${type === "intent" ? "center" : ""}">
      <div class="col-head"><span class="tdot" style="background:${TYPE_COLOR[type]}"></span>${label}<span class="faint">${lists[ci].length}</span></div>
      ${lists[ci].map((id) => {
        const n = byId.get(id);
        return `<button class="gnode t-${type} ${gapIds.has(id) ? "gap" : ""}" style="--type:${TYPE_COLOR[type]}" data-act="select-node" data-id="${esc(id)}" data-node="${esc(id)}" title="${esc(unflag(n.label))}">
          <span class="ghead"><span class="gid">${esc(id)}</span>${gapIds.has(id) ? '<span class="gap-tag">gap</span>' : ""}</span>
          <span class="lbl">${esc(unflag(n.label))}</span></button>`;
      }).join("") || '<span class="empty" style="text-align:center">none</span>'}</div>`).join("");
  const markers = Object.keys(RELATIONS).map((rel) => `<marker id="arrow-${rel}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8 z" fill="${relColor(rel)}"/></marker>`).join("");
  return `${filters}
    <div class="trace-wrap"><div>
      <div class="graph" id="graph" style="--cols:${cols.length}"><svg class="edges" id="edges"><defs>${markers}</defs><g id="edgePaths"></g></svg><div class="graph-cols">${colHtml}</div></div>
    </div>${traceDetail(g)}</div>
    ${traceLegend()}
    <div class="card" style="margin-top:14px"><div class="card-head"><h2>Gaps</h2><span class="badge ${g.gaps.length ? "bad" : "ok"}">${g.gaps.length}</span><span class="small faint">Things that should be traced but are not. Click one to find it in the graph.</span></div>
      ${g.gaps.length ? `<div class="gaps">${g.gaps.map((x) => `<button class="gap-row" ${x.artifact_id ? `data-act="select-node" data-id="${esc(x.artifact_id)}"` : ""} title="${esc(GAP_DEF[x.kind] || "")}"><span class="pill warn">${esc(x.kind.replaceAll("_", " "))}</span><span class="gtext">${esc(x.detail)}</span></button>`).join("")}</div>` : '<div class="empty">Every artifact is linked.</div>'}</div>`;
}

function traceLegend() {
  return `<div class="card legend-card">
    <div><h3>Artifacts (columns)</h3><div class="legend-rows">
      ${GRAPH_COLS.map(([t]) => `<div class="legend-row"><span class="legend-node" style="border-left:3px solid ${TYPE_COLOR[t]}"><span class="tdot" style="background:${TYPE_COLOR[t]}"></span></span><span>${typeWord(t)}: ${esc(TYPE_DEF[t])}</span></div>`).join("")}
    </div></div>
    <div><h3>Trace links</h3><p class="small faint" style="margin:0 0 8px">Each arrow points from an artifact to the one it traces up to. Its colour is the type it starts from.</p><div class="legend-rows">
      ${Object.entries(RELATIONS).map(([rel, r]) => `<div class="legend-row">${linkSample(rel)}<span>${typeWord(r.from)} ${r.verb} ${typeWord(r.to)}<span class="faint">: ${esc(r.def)}</span></span></div>`).join("")}
    </div></div>
    <div><h3>Markers</h3><div class="legend-rows">
      <div class="legend-row"><span class="gnode gap legend-node" style="--type:#9b9ca5"><span class="gap-tag">gap</span></span><span>Dashed amber outline: the artifact has a trace gap (see the glossary).</span></div>
      <div class="legend-row">${linkSample(null, 46, true)}<span>Dashed link: it skips a column. Hidden until you hover over or select a node, unless "Show links that skip a column" is on.</span></div>
      <div class="legend-row"><span class="legend-node focus-sample"></span><span>Hover over a node to light up everything it traces to and from; click to pin it and open its details.</span></div>
      <div class="legend-row"><span class="type-chip off" style="pointer-events:none"><span class="tdot" style="background:#9b9ca5"></span>Type</span><span>Click a type above the graph to hide or show that column.</span></div>
    </div>
    <h3 style="margin-top:14px">Gap glossary</h3><dl class="gap-glossary">
      ${Object.entries(GAP_DEF).map(([k, d]) => `<dt>${esc(k.replaceAll("_", " "))}</dt><dd>${esc(d)}</dd>`).join("")}
    </dl></div>
  </div>`;
}

function traceDetail(g) {
  const n = g.nodes.find((x) => x.id === S.selected);
  if (!n) return `<div class="card detail"><h2>Select an artifact</h2><p class="small muted">Click a node to pin its trace and see what it links to and the PRD quote behind it.</p></div>`;
  const key = nodeKey(n);
  const out = g.edges.filter((e) => e.source === n.id), inc = g.edges.filter((e) => e.target === n.id);
  const linkRow = (e, other, outgoing) => {
    const r = RELATIONS[e.relation] || { verb: e.relation };
    const chip = `<button class="chip" data-act="select-node" data-id="${esc(other)}">${esc(other)}</button>`;
    return `<div class="legend-row">${linkSample(e.relation, 30)}<span>${outgoing ? `${r.verb} ${chip}` : `${chip} ${r.verb} this`}</span></div>`;
  };
  const quotes = n.type === "intent" ? (n.data.sson_evidence || []) : n.data.source ? [n.data.source] : [];
  const gaps = g.gaps.filter((x) => x.artifact_id === n.id);
  return `<div class="card detail"><div class="card-head"><span class="tdot" style="background:${TYPE_COLOR[n.type]}"></span><span class="iid" style="color:${TYPE_COLOR[n.type]}">${esc(n.id)}</span><span class="small muted">${TYPE_NAME[n.type]}</span>${statusPill(key)}</div>
    <div style="margin-bottom:10px">${esc(unflag(n.label))}</div>
    ${gaps.map((x) => `<div class="quote missing">${esc(x.detail)}</div>`).join("")}
    ${out.length ? `<h3 style="margin-top:10px">Traces to</h3><div class="legend-rows">${out.map((e) => linkRow(e, e.target, true)).join("")}</div>` : ""}
    ${inc.length ? `<h3 style="margin-top:10px">Traced from</h3><div class="legend-rows">${inc.map((e) => linkRow(e, e.source, false)).join("")}</div>` : ""}
    ${n.type === "use_case" ? "" : `<h3 style="margin-top:10px">PRD source</h3>${quotes.length ? quotes.map((q) => `<div class="quote">“${esc(q)}”</div>`).join("") : '<div class="quote missing">No PRD quote</div>'}`}
    <div class="actions" style="margin-top:12px"><button class="btn" data-act="jump" data-key="${esc(key)}">Open on its page →</button><button class="btn ghost" data-act="select-node" data-id="">Clear</button></div></div>`;
}

function drawEdges() {
  const graph = $("#graph"), paths = $("#edgePaths");
  const g = st().artifact_graph;
  if (!graph || !paths || !g) return;
  const box = graph.getBoundingClientRect();
  const rect = (id) => graph.querySelector(`[data-node="${CSS.escape(id)}"]`)?.getBoundingClientRect();
  const cols = visibleCols();
  const colOf = (id) => cols.findIndex(([t]) => t === g.nodes.find((n) => n.id === id)?.type);
  const svg = $("#edges");
  svg.setAttribute("width", graph.scrollWidth);
  svg.setAttribute("height", graph.scrollHeight);
  paths.innerHTML = g.edges.map((e) => {
    const a = rect(e.source), b = rect(e.target);
    if (!a || !b) return "";
    const ca = colOf(e.source), cb = colOf(e.target);
    const ltr = ca < cb;
    const x1 = (ltr ? a.right : a.left) - box.left + graph.scrollLeft, y1 = a.top + a.height / 2 - box.top;
    const x2 = (ltr ? b.left : b.right) - box.left + graph.scrollLeft, y2 = b.top + b.height / 2 - box.top;
    const dx = Math.max(24, Math.abs(x2 - x1) * 0.5) * (ltr ? 1 : -1);
    const long = Math.abs(ca - cb) > 1 ? "long" : "";
    return `<path class="${long}" data-s="${esc(e.source)}" data-t="${esc(e.target)}" stroke="${relColor(e.relation)}" marker-end="url(#arrow-${e.relation})" d="M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2 - (ltr ? 2 : -2)},${y2}"><title>${esc(e.source)} ${esc(RELATIONS[e.relation]?.verb || e.relation)} ${esc(e.target)}</title></path>`;
  }).join("");
  graph.classList.toggle("show-long", !!S.traceShowLong);
  applyFocus(S.selected);
}

function applyFocus(id) {
  // highlight one artifact's trace without re-rendering (used for hover and selection)
  const graph = $("#graph"), g = st().artifact_graph;
  if (!graph || !g) return;
  const near = id ? neighbourhood(g, id) : null;
  graph.classList.toggle("focus", !!near);
  graph.querySelectorAll(".gnode").forEach((n) => {
    n.classList.toggle("near", !!near?.has(n.dataset.node));
    n.classList.toggle("on", n.dataset.node === S.selected);
  });
  graph.querySelectorAll("#edgePaths path").forEach((p) => p.classList.toggle("hot", !!near && near.has(p.dataset.s) && near.has(p.dataset.t)));
}

/* ---------- trace: impact analysis ---------- */
const PROPOSAL_KIND = {
  revise: ["warn", "Revise"], remove: ["bad", "Remove"], unlink: ["info", "Remove link"],
  add: ["violet", "Add"], rerun: ["info", "Rebuild"],
};
const shortKey = (key) => (key === "singleton:sson" ? "SSON" : key === "singleton:situation" ? "Current situation" : (key || "").split(":")[1] || key);

function pendingChanges() {
  return (S.session?.changes || []).filter((c) => !c.analyzed_in);
}
function openSuggestions() {
  const map = new Map();
  for (const r of S.session?.impact_reports || []) {
    if (r.status !== "open") continue;
    for (const p of r.proposals) if (p.status === "pending" && p.key) map.set(p.key, (map.get(p.key) || 0) + 1);
  }
  return map;
}

function impactBanner() {
  const s = S.session;
  if (!s || S.page === "welcome" || (S.page === "trace" && S.traceTab === "impact")) return "";
  if (s.running && s.run?.impact) return `<div class="banner running"><span class="spinner"></span><div class="msg"><b>Analyzing impact</b>The impact analysis agent is checking the artifacts linked to your edits.</div></div>`;
  const pending = pendingChanges();
  const open = (s.impact_reports || []).filter((r) => r.status === "open");
  const waiting = open.reduce((n, r) => n + r.proposals.filter((p) => p.status === "pending").length, 0);
  if (pending.length) return `<div class="banner impact"><div class="msg"><b>${plural(pending.length, "edit")} since the last impact analysis</b>The agent checks what your edits mean for the artifacts traced to them and suggests changes; nothing changes until you accept.</div>
    <button class="btn primary" data-act="analyze-impact" ${dis()}>Analyze impact</button><button class="btn ghost" data-act="open-impact">Details</button></div>`;
  if (waiting) return `<div class="banner impact"><div class="msg"><b>${plural(waiting, "suggested change")} waiting</b>From impact analysis ${esc(open.map((r) => r.report_id).join(", "))}.</div><button class="btn primary" data-act="open-impact">Review</button></div>`;
  return "";
}

function wordDiff(before, after) {
  // longest common subsequence on words: unchanged words plain, the rest marked
  const a = String(before || "").split(/\s+/).filter(Boolean), b = String(after || "").split(/\s+/).filter(Boolean);
  const dp = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) for (let j = b.length - 1; j >= 0; j--)
    dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out = [];
  let i = 0, j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) { out.push(esc(a[i])); i++; j++; }
    else if (j < b.length && (i === a.length || dp[i][j + 1] >= dp[i + 1][j])) { out.push(`<ins>${esc(b[j])}</ins>`); j++; }
    else { out.push(`<del>${esc(a[i])}</del>`); i++; }
  }
  return out.join(" ");
}

function fieldDiff(p) {
  const show = (v) => (Array.isArray(v) ? (v.length ? v.map((x) => (typeof x === "object" ? x.name : x)).join(", ") : "∅") : v === null || v === undefined || v === "" ? "∅" : String(v));
  if (p.kind === "add") return Object.entries(p.fields).map(([f, v]) => `<div><span class="f">${esc(f)}</span> <ins>${esc(show(v))}</ins></div>`).join("");
  if (p.kind === "remove") return `<div><del>${esc(unflag(p.label))}</del></div>`;
  return Object.entries(p.fields).map(([f, v]) => typeof v === "string" && typeof p.before?.[f] === "string"
    ? `<div><span class="f">${esc(f)}</span> ${wordDiff(p.before[f], v)}</div>`
    : `<div><span class="f">${esc(f)}</span> <del>${esc(show(p.before?.[f]))}</del> → <ins>${esc(show(v))}</ins></div>`).join("");
}

function traceImpact() {
  const s = S.session;
  const pending = pendingChanges();
  const busy = s.running && s.run?.impact;
  const head = `<div class="card"><div class="card-head"><h2>Impact analysis</h2><span class="grow"></span>
      <button class="btn primary" data-act="analyze-impact" ${pending.length && !running() ? "" : "disabled"}>Analyze ${pending.length ? plural(pending.length, "edit") : "impact"}</button></div>
    <p class="small muted" style="margin:0">After you edit artifacts, the agent follows the trace links from each edit (two steps out, plus anything that refers to a deleted artifact), decides for each linked artifact whether it is unaffected, needs revising or is obsolete, and suggests the changes. Removing links to deleted artifacts needs no model. Nothing changes until you accept a suggestion; closing a report marks the stages it checked as reviewed.</p>
    ${busy ? '<div class="banner running" style="margin:12px 0 0"><span class="spinner"></span><div class="msg"><b>Analyzing…</b></div></div>' : ""}
    ${pending.length ? `<div class="links"><span class="kind">Edits waiting</span>${pending.map((c) => `<button class="chip" data-act="jump" data-key="${esc(c.key)}" title="${esc(c.action)} ${esc(time(c.at))}">${esc(shortKey(c.key))}</button><span class="small faint">${esc(c.action)}</span>`).join(" ")}</div>` : ""}</div>`;
  const reports = [...(s.impact_reports || [])].reverse().map((r) => {
    const open = r.status === "open";
    const waiting = r.proposals.filter((p) => p.status === "pending").length;
    const proposals = r.proposals.map((p) => {
      const [cls, label] = PROPOSAL_KIND[p.kind] || ["neutral", p.kind];
      const target = p.key ? `<button class="chip" data-act="jump" data-key="${esc(p.key)}">${esc(shortKey(p.key))}</button>` : `<span class="pill neutral">${esc(p.kind === "rerun" ? p.label : "new " + (COLL_LABEL[p.collection] || p.type))}</span>`;
      const decided = p.status !== "pending" ? `<span class="pill ${p.status === "accepted" ? "ok" : "neutral"}">${esc(p.status)}</span>` : "";
      const buttons = p.status === "pending" && open ? `<span class="grow"></span><span class="actions"><button class="btn ok" data-act="decide" data-report="${esc(r.report_id)}" data-proposal="${esc(p.proposal_id)}" data-decision="accept" ${dis()}>Accept</button><button class="btn ghost" data-act="decide" data-report="${esc(r.report_id)}" data-proposal="${esc(p.proposal_id)}" data-decision="reject" ${dis()}>Reject</button></span>` : "";
      return `<div class="item proposal ${p.status}"><div class="item-head"><span class="iid">${esc(p.proposal_id)}</span><span class="pill ${cls}">${label}</span>${target}${decided}${buttons}</div>
        <div class="item-text small">${esc(p.reason)}</div><div class="diff">${fieldDiff(p)}</div></div>`;
    }).join("") || '<div class="empty">No changes suggested: every linked artifact is still consistent.</div>';
    return `<div class="card"><div class="card-head"><h2>${esc(r.report_id)}</h2><span class="pill ${open ? "info" : "neutral"}">${open ? "open" : "closed"}</span>
        <span class="small faint">${esc(dateTime(r.at))} · ${plural(r.candidates.length, "linked artifact")} checked</span><span class="grow"></span>
        ${open ? `<button class="btn" data-act="close-report" data-report="${esc(r.report_id)}" ${dis()} title="Marks ${esc((r.stages || []).join(", "))} as reviewed">${waiting ? "Close, leaving " + waiting + " undecided" : "Close and mark reviewed"}</button>` : ""}</div>
      <div class="links"><span class="kind">Edits analyzed</span>${r.changes.map((c) => `<button class="chip" data-act="jump" data-key="${esc(c.key)}">${esc(shortKey(c.key))}</button><span class="small faint">${esc(c.action)}</span>`).join(" ")}</div>
      <h3 style="margin-top:14px">Suggested changes</h3><div class="list">${proposals}</div>
      ${r.unaffected.length ? `<details style="margin-top:12px"><summary class="small muted">${plural(r.unaffected.length, "linked artifact")} unaffected</summary><div class="unaffected">${r.unaffected.map((u) => `<div class="small"><span class="iid">${esc(u.artifact_id)}</span> <span class="muted">${esc(u.reason)}</span></div>`).join("")}</div></details>` : ""}
      ${r.notes.length ? `<details style="margin-top:8px"><summary class="small muted">${plural(r.notes.length, "note")}</summary><ul class="checks-list">${r.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul></details>` : ""}
    </div>`;
  }).join("");
  return head + (reports || '<div class="empty">No impact analysis yet. Edit an artifact, then analyze its impact here.</div>');
}

/* ---------- trace: PRD coverage ---------- */
function coverage() {
  const prd = st().prd || "";
  const sources = [];
  for (const coll of Object.keys(COLL_LABEL)) {
    for (const item of list(coll)) if (item.source) sources.push({ id: idOf(coll, item), key: `${coll}:${idOf(coll, item)}`, quote: item.source });
  }
  for (const q of intent().sson_evidence || []) sources.push({ id: "SSON", key: "singleton:sson", quote: q, evidence: true });
  const reEsc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const ranges = [], unplaced = [];
  for (const s of sources) {
    const words = s.quote.trim().split(/\s+/).map(reEsc);
    const m = words.length ? new RegExp(words.join("\\s+"), "i").exec(prd) : null;
    if (m) ranges.push({ ...s, start: m.index, end: m.index + m[0].length }); else unplaced.push(s);
  }
  const cuts = [...new Set([0, prd.length, ...ranges.flatMap((r) => [r.start, r.end])])].sort((a, b) => a - b);
  const segments = [];
  let covered = 0;
  for (let i = 0; i < cuts.length - 1; i++) {
    const [a, b] = [cuts[i], cuts[i + 1]];
    const hits = ranges.filter((r) => r.start <= a && r.end >= b);
    const text = prd.slice(a, b);
    if (hits.length) covered += text.replace(/\s/g, "").length;
    segments.push({ text, hits });
  }
  const total = prd.replace(/\s/g, "").length || 1;
  const noSource = [];
  for (const coll of Object.keys(COLL_LABEL)) {
    if (coll === "stakeholders" || coll === "personas") continue;
    for (const item of list(coll)) if (!item.source) noSource.push({ id: idOf(coll, item), key: `${coll}:${idOf(coll, item)}` });
  }
  return { segments, percent: Math.round((100 * covered) / total), unplaced, noSource, count: sources.length };
}

function tracePrd(cov) {
  const sel = S.covSelected;
  const html = cov.segments.map((s, i) => {
    if (!s.hits.length) return esc(s.text);
    const ids = [...new Set(s.hits.map((h) => h.id))];
    const ev = s.hits.every((h) => h.evidence);
    const on = sel !== null && cov.segments[sel] && ids.some((x) => cov.segments[sel].hits.some((h) => h.id === x));
    return `<mark class="cov n${Math.min(ids.length, 3)} ${ev ? "ev" : ""} ${on ? "on" : ""}" data-act="cov" data-seg="${i}" title="${esc(ids.join(", "))}">${esc(s.text)}</mark>`;
  }).join("");
  const selHits = sel !== null && cov.segments[sel] ? cov.segments[sel].hits : [];
  return `<div class="cov-wrap"><div class="card"><div class="card-head"><h2>PRD</h2><span class="small faint">Highlighted text is quoted by at least one artifact; darker means more. Blue is SSON evidence. Click a highlight.</span></div>
      <pre class="prd" style="max-height:none">${html}</pre></div>
    <div class="card detail"><h2>${selHits.length ? "Quoted by" : "Coverage"}</h2>
      ${selHits.length ? `<div class="links">${[...new Map(selHits.map((h) => [h.key, h])).values()].map((h) => `<button class="chip" data-act="jump" data-key="${esc(h.key)}">${esc(h.id)}</button>`).join("")}</div>`
        : `<p class="small muted">${cov.count} quotes cover ${cov.percent}% of the PRD's text.</p>`}
      <h3 style="margin-top:14px">Items with no PRD quote</h3>
      ${cov.noSource.length ? `<div class="links">${cov.noSource.map((x) => `<button class="chip" data-act="jump" data-key="${esc(x.key)}">${esc(x.id)}</button>`).join("")}</div>` : '<div class="small faint">None</div>'}
      ${cov.unplaced.length ? `<h3 style="margin-top:14px">Quotes not located</h3><p class="small faint">The backend matched these, but the highlighter could not place them (punctuation differences).</p><div class="links">${cov.unplaced.map((x) => `<button class="chip" data-act="jump" data-key="${esc(x.key)}">${esc(x.id)}</button>`).join("")}</div>` : ""}
    </div></div>`;
}

function traceLog() {
  const s = S.session;
  return `<div class="card"><div class="card-head"><h2>Activity</h2><span class="badge">${s.events.length}</span><span class="grow"></span>
    <span class="small faint">${plural(s.snapshots.length, "replaced output")} kept from re-runs</span></div>
    <ul class="timeline">${[...s.events].reverse().map(eventRow).join("")}</ul></div>`;
}

/* ---------- events ---------- */
function readForm(form) {
  const fields = {};
  for (const el of form.elements) {
    if (!el.name) continue;
    if (el.type === "checkbox") { (fields[el.name] ||= []); if (el.checked) fields[el.name].push(el.value); }
    else fields[el.name] = el.value;
  }
  return fields;
}

function goalExtras(form, fields) {
  return {
    benefit_ids: fields.benefit_ids || [],
    actors: [...form.querySelectorAll(".actor-row")].map((row) =>
      Object.fromEntries([...row.querySelectorAll("[data-actor]")].map((i) => [i.dataset.actor, i.value]))),
  };
}

async function onSubmit(e) {
  const form = e.target.closest("form[data-form]");
  if (!form) return;
  e.preventDefault();
  const key = form.dataset.form;
  const fields = readForm(form);
  const sid = S.session.id;
  if (key.startsWith("singleton:")) {
    const name = key.split(":")[1];
    if (name === "sson" && unflag(intent().single_statement_intent) === fields.single_statement_intent.trim())
      fields.single_statement_intent = intent().single_statement_intent; // unchanged: keep its flag
    await mutate("PATCH", `/api/sessions/${sid}/singletons/${name}`, { fields }, "Saved");
    return;
  }
  const coll = form.dataset.coll;
  if (key.startsWith("new:")) {
    if (coll === "benefits" && !fields.addresses) fields.addresses = [];
    if (coll === "goals") Object.assign(fields, goalExtras(form, fields));
    await mutate("POST", `/api/sessions/${sid}/items/${coll}`, { fields }, `Added ${COLL_LABEL[coll]}`);
  } else {
    const id = key.split(":")[1];
    const item = list(coll).find((i) => idOf(coll, i) === id);
    if (fields.description !== undefined && unflag(item.description) === fields.description.trim()) fields.description = item.description;
    if (fields.statement !== undefined && unflag(item.statement) === fields.statement.trim()) fields.statement = item.statement;
    if (coll === "benefits" && !fields.addresses) fields.addresses = [];
    if (coll === "goals") Object.assign(fields, goalExtras(form, fields));
    await mutate("PATCH", `/api/sessions/${sid}/items/${coll}/${id}`, { fields }, `Saved ${id}`);
  }
}

function rerunImpact(stage, cascade) {
  const stages = [stage, ...(cascade ? S.config.downstream[stage] || [] : [])];
  const colls = [];
  for (const s of stages) {
    if (s === "sson") colls.push("singleton:sson");
    if (s === "context") colls.push("singleton:situation", ...CONTEXT_SECTIONS.map((x) => x.coll));
    if (["stakeholders", "personas", "goals"].includes(s)) colls.push(s);
  }
  let touched = 0;
  for (const [key, m] of Object.entries(S.session.items)) {
    if (colls.some((c) => key === c || key.startsWith(c + ":")) && ["edited", "added", "accepted"].includes(m.status)) touched++;
  }
  return { stages, touched };
}

const ACTIONS = {
  nav: (d) => go(d.page),
  "close-tab": (d, e) => {
    e.stopPropagation();
    S.tabs = S.tabs.filter((t) => t !== d.page);
    if (S.page === d.page) go(S.tabs.at(-1) || "welcome"); else render();
  },
  scroll: (d) => document.getElementById(d.target)?.scrollIntoView({ behavior: "smooth", block: "start" }),
  jump: (d) => jump(d.key),
  "new-session": () => { S.composing = true; S.prd = ""; go("welcome"); },
  "cancel-compose": () => { S.composing = false; render(); },
  "open-session": async (d) => {
    try { S.composing = false; S.editing = null; setSession(await api("GET", `/api/sessions/${d.sid}`)); go("welcome"); }
    catch (e) { toast(e.message, true); }
  },
  run: async () => {
    const prd = S.prd.trim();
    if (!prd) return;
    try {
      const session = await api("POST", "/api/sessions", { prd: S.prd });
      S.composing = false; S.showDeleted.clear(); S.selected = null;
      S.tabs = ["welcome"];
      setSession(session);
      refreshSessions();
    } catch (e) { toast(e.message, true); }
  },
  edit: (d) => { S.editing = d.key; S.formError = null; render(); requestAnimationFrame(() => document.querySelector(`[data-form="${CSS.escape(d.key)}"] .input`)?.focus()); },
  add: (d) => { S.editing = `new:${d.coll}`; S.formError = null; render(); requestAnimationFrame(() => document.querySelector(`[data-form="new:${d.coll}"] .input`)?.focus()); },
  "add-actor": (d, e, el) => el.closest("form").querySelector(".actors-edit").insertAdjacentHTML("beforeend", actorRow()),
  "remove-actor": (d, e, el) => el.closest(".actor-row").remove(),
  "cancel-edit": () => { S.editing = null; S.formError = null; render(); },
  "toggle-deleted": (d) => { S.showDeleted.has(d.coll) ? S.showDeleted.delete(d.coll) : S.showDeleted.add(d.coll); render(); },
  accept: (d) => d.coll.startsWith("singleton:")
    ? mutate("POST", `/api/sessions/${S.session.id}/accept/${d.coll}`, {}, "Accepted")
    : mutate("POST", `/api/sessions/${S.session.id}/accept/${d.coll}`, { ids: [d.id] }, `Accepted ${d.id}`),
  "accept-all": (d) => mutate("POST", `/api/sessions/${S.session.id}/accept/${d.coll}`, {}, "Accepted all proposed"),
  delete: async (d) => {
    let body = `${esc(d.id)} moves to the deleted list. You can restore it later.`;
    if (d.coll === "problems") {
      const refs = list("benefits").filter((b) => (b.addresses || []).includes(d.id)).map((b) => b.id);
      if (refs.length) body += ` ${esc(refs.join(", "))} address${refs.length === 1 ? "es" : ""} it, so the trace will show a broken link.`;
    }
    if (d.coll === "benefits") {
      const refs = list("goals").filter((g) => (g.benefit_ids || []).includes(d.id)).map((g) => g.goal_id);
      if (refs.length) body += ` ${esc(refs.join(", "))} deliver${refs.length === 1 ? "s" : ""} it, so the trace will show a broken link.`;
    }
    if (d.coll === "stakeholders") {
      const refs = [...list("personas").filter((p) => p.stakeholder_id === d.id).map((p) => p.persona_id),
        ...list("goals").filter((g) => (g.actors || []).some((a) => a.stakeholder_id === d.id)).map((g) => g.goal_id)];
      if (refs.length) body += ` ${esc(refs.join(", "))} link${refs.length === 1 ? "s" : ""} to it and will show a broken link.`;
    }
    if (await confirmModal({ title: `Delete ${d.id}?`, body, ok: "Delete", danger: true }))
      mutate("DELETE", `/api/sessions/${S.session.id}/items/${d.coll}/${d.id}`, undefined, `Deleted ${d.id}`);
  },
  restore: (d) => mutate("POST", `/api/sessions/${S.session.id}/items/${d.coll}/${d.id}/restore`, undefined, `Restored ${d.id}`),
  rerun: async (d) => {
    const cascade = d.cascade === "1";
    const { stages, touched } = rerunImpact(d.stage, cascade);
    const labels = stages.map((s) => S.config.stages.find((x) => x.id === s).label).join(", ");
    const body = `Runs: ${esc(labels)} on <span class="mono">${esc(S.config.model)}</span>.${touched ? ` <b>${plural(touched, "reviewed item")}</b> will be replaced by fresh output; the previous output is kept in the session.` : ""}`;
    if (d.stage === "sson_eval" || await confirmModal({ title: "Re-run?", body, ok: "Re-run" }))
      mutate("POST", `/api/sessions/${S.session.id}/rerun`, { stage: d.stage, cascade }, "Re-run started");
  },
  keep: (d) => mutate("POST", `/api/sessions/${S.session.id}/stages/${d.stage}/keep`, undefined, "Kept as is"),
  "trace-tab": (d) => { S.traceTab = d.tab; render(); },
  "toggle-type": (d) => { S.traceHidden.has(d.type) ? S.traceHidden.delete(d.type) : S.traceHidden.add(d.type); render(); },
  "toggle-long": (d, e, el) => { S.traceShowLong = el.checked; $("#graph")?.classList.toggle("show-long", S.traceShowLong); },
  "open-impact": () => { S.traceTab = "impact"; go("trace"); },
  "analyze-impact": () => mutate("POST", `/api/sessions/${S.session.id}/impact`, undefined, "Impact analysis started"),
  "decide": (d) => mutate("POST", `/api/sessions/${S.session.id}/impact/${d.report}/proposals/${d.proposal}`, { decision: d.decision }, d.decision === "accept" ? `Applied ${d.proposal}` : `Rejected ${d.proposal}`),
  "close-report": (d) => mutate("POST", `/api/sessions/${S.session.id}/impact/${d.report}/close`, undefined, `Closed ${d.report}`),
  "select-node": (d) => { S.selected = d.id || null; render(); },
  cov: (d) => { S.covSelected = Number(d.seg); render(); },
};

document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-act]");
  if (!el || el.disabled) return;
  const fn = ACTIONS[el.dataset.act];
  if (fn) fn(el.dataset, e, el);
});
document.addEventListener("submit", onSubmit);
document.addEventListener("input", (e) => {
  if (e.target.id !== "prdInput") return;
  const shape = () => `${!S.prd.trim()}`;
  const before = shape();
  S.prd = e.target.value;
  if (shape() !== before) {
    // re-render controls without losing the caret in the textarea
    const { selectionStart, selectionEnd } = e.target;
    render();
    const ta = $("#prdInput");
    ta.focus();
    ta.setSelectionRange(selectionStart, selectionEnd);
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && S.editing) ACTIONS["cancel-edit"]();
});
window.addEventListener("resize", () => S.page === "trace" && drawEdges());
let hoveredCase = null;
document.addEventListener("mouseover", (e) => {
  if (S.page !== "usecases") return;
  const id = e.target.closest?.("#ucd [data-uc-node]")?.dataset.ucNode || null;
  if (id !== hoveredCase) { hoveredCase = id; focusUseCase(id); }
});
let hovered = null;
document.addEventListener("mouseover", (e) => {
  if (S.page !== "trace" || S.traceTab !== "graph") return;
  const node = e.target.closest?.("#graph .gnode")?.dataset.node || null;
  if (node === hovered) return;
  hovered = node;
  applyFocus(node || S.selected);
});
window.addEventListener("hashchange", () => go(location.hash.slice(1)));

/* ---------- boot ---------- */
(async function boot() {
  try {
    S.config = await api("GET", "/api/config");
  } catch (e) {
    $("#view").innerHTML = `<div class="banner error"><div class="msg"><b>Cannot reach the backend</b>${esc(e.message)}. Start it from src/ with <span class="mono">uvicorn agentic_flow.api.server:app --port 8000</span>.</div></div>`;
    return;
  }
  S.page = PAGE[location.hash.slice(1)] ? location.hash.slice(1) : "welcome";
  const tab = new URLSearchParams(location.search).get("tab");
  if (["graph", "impact", "prd", "log"].includes(tab)) S.traceTab = tab;
  S.tabs = [...new Set(["welcome", S.page])];
  await refreshSessions();
  const saved = new URLSearchParams(location.search).get("session") || recall("ide3.session");
  if (saved && S.sessions.some((x) => x.id === saved)) {
    try { S.session = await api("GET", `/api/sessions/${saved}`); } catch (_) { store("ide3.session", null); }
  }
  render();
  schedulePoll();
})();
