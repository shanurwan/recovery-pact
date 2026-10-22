// RecoveryPact operator console. Vanilla JS, no build step.
"use strict";

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = async (path, opts = {}) => {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
};

const state = { run: null, evidence: {}, source: null, busy: false, scenarios: [] };

const ACTOR = {
  database_guardian: { label: "Database Guardian", cls: "db" },
  continuity_guardian: { label: "Continuity Guardian", cls: "cg" },
  solo_agent: { label: "Single agent", cls: "db" },
  authority: { label: "Authority", cls: "au" },
  executor: { label: "Restricted executor", cls: "au" },
  verifier: { label: "Verifier", cls: "au" },
  eval_judge: { label: "Eval judge", cls: "au" },
  zetaris: { label: "Zetaris", cls: "evid" },
  observer: { label: "PostgreSQL observer", cls: "evid" },
  business_calculator: { label: "Business calculator", cls: "evid" },
  meterless_hmem: { label: "Meterless H-MEM", cls: "evid" },
  grounding_check: { label: "Grounding check", cls: "au" },
  simulator: { label: "Simulator", cls: "bad" },
  detector: { label: "Detector", cls: "bad" },
  orchestrator: { label: "Orchestrator", cls: "" },
  pact: { label: "Pact", cls: "" },
  human: { label: "Human", cls: "au" },
  recovery_auditor: { label: "Recovery Auditor", cls: "cg" },
};
const SOURCE_LABEL = {
  zetaris: "Zetaris",
  local_federation_fallback: "Local fallback",
  postgresql_observer: "PostgreSQL",
  checkout_telemetry: "Telemetry",
  meterless_hmem: "H-MEM",
};

// ------------------------------------------------------------------ status

async function refreshStatus() {
  try {
    const s = await api("/api/status");
    const inf = s.inference.mode === "nemotron" ? "live" : s.inference.mode;
    const model = s.inference.model.replace("nvidia/", "");
    $("#chips").innerHTML = [
      `<span class="chip ${inf === "live" ? "live" : "fallback"}">NVIDIA <b>${esc(model)}</b> · ${esc(inf)}</span>`,
      `<span class="chip ${s.zetaris.mode === "zetaris" ? "live" : "fallback"}">Zetaris · <b>${s.zetaris.mode === "zetaris" ? "live federation" : "local fallback"}</b></span>`,
      `<span class="chip live">Meterless H-MEM · <b>${s.memory.count}</b> memories</span>`,
    ].join("");
    const c = s.checkout;
    const succ = $("#kpi-success");
    succ.textContent = c.total ? `${Math.round(c.success_rate * 100)}%` : "–";
    succ.className = "kpi-value " + (c.success_rate < 0.95 ? "bad" : "ok");
    const failed = c.failed_count + c.timeout_count;
    $("#kpi-failed").textContent = failed;
    $("#kpi-failed").className = "kpi-value " + (failed ? "bad" : "ok");
    $("#kpi-incident").textContent = s.incident ? `${s.incident.title} (pid ${s.incident.blocker_pid})` : "none";
    state.busy = s.busy;
    document.querySelectorAll(".sc").forEach((b) => (b.disabled = s.busy));
  } catch (e) { /* api restarting */ }
}

async function refreshSpark() {
  try {
    const rows = await api("/api/checkout/series?seconds=120");
    const svg = $("#spark");
    const w = svg.clientWidth || 600, h = svg.clientHeight || 46;
    const now = Math.floor(Date.now() / 1000);
    const byT = Object.fromEntries(rows.map((r) => [r.t, r]));
    const n = 120, bw = w / n;
    const max = Math.max(4, ...rows.map((r) => r.ok + r.bad));
    let out = "";
    for (let i = 0; i < n; i++) {
      const r = byT[now - n + i] || { ok: 0, bad: 0 };
      const hb = (r.bad / max) * h, ho = (r.ok / max) * h;
      if (ho) out += `<rect x="${i * bw}" y="${h - ho}" width="${Math.max(1, bw - 1)}" height="${ho}" fill="var(--ok)" opacity=".85"/>`;
      if (hb) out += `<rect x="${i * bw}" y="${h - ho - hb}" width="${Math.max(1, bw - 1)}" height="${hb}" fill="var(--bad)"/>`;
    }
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    svg.innerHTML = out;
  } catch (e) { /* ignore */ }
}

// --------------------------------------------------------------- scenarios

async function loadScenarios() {
  state.scenarios = await api("/api/scenarios");
  $("#scenarios").innerHTML = state.scenarios
    .map(
      (s) => `<button class="sc" data-id="${esc(s.id)}" title="${esc(s.story)}">
        <span class="id">${esc(s.id.split("_")[0])}</span>
        <span class="t">${esc(s.title)}</span>
        <span class="exp">Correct: ${esc(s.expected_action.toLowerCase())} → ${esc(s.expected_outcome.replace("_", " ").toLowerCase())}</span>
      </button>`
    )
    .join("");
  document.querySelectorAll(".sc").forEach((b) => b.addEventListener("click", () => startRun(b.dataset.id)));
}

async function startRun(scenario) {
  try {
    const run = await api("/api/runs", {
      method: "POST",
      body: JSON.stringify({ scenario, arch: $("#arch").value, use_memory: $("#mem").checked }),
    });
    watchRun(run.run_id, run);
  } catch (e) {
    alert(e.message);
  }
}

// ---------------------------------------------------------------- timeline

function watchRun(runId, summary) {
  if (state.source) state.source.close();
  state.run = { run_id: runId, ...summary };
  state.evidence = {};
  $("#timeline").innerHTML = "";
  const sc = state.scenarios.find((s) => s.id === summary.scenario);
  $("#tl-title").textContent = `${sc ? sc.title : summary.scenario} · ${summary.arch}`;
  setStatus(summary.status || "running");
  $("#tab-receipt").innerHTML = `<p class="muted">Run in progress…</p>`;
  const src = new EventSource(`/api/runs/${runId}/events`);
  state.source = src;
  src.addEventListener("pact", (m) => renderEvent(JSON.parse(m.data)));
  src.addEventListener("end", (m) => {
    const s = JSON.parse(m.data);
    src.close();
    setStatus(s.status);
    loadReceipt(runId);
    refreshMemory();
    refreshHistory();
  });
  src.onerror = () => { src.close(); setTimeout(() => loadReceipt(runId), 1500); };
}

function setStatus(s) {
  const el = $("#tl-status");
  el.textContent = s.replace("_", " ");
  el.className = "status " + s;
}

function cites(ids) {
  return ids && ids.length
    ? `<div class="cites">${ids.map((i) => `<span class="cite" data-ev="${esc(i)}">${esc(i)}</span>`).join("")}</div>`
    : "";
}

function evidenceBody(ev) {
  if (!ev) return "";
  state.evidence[ev.evidence_id] = ev;
  const q = ev.query ? `<details><summary>Federated SQL${ev.latency_ms ? ` · ${ev.latency_ms} ms` : ""}</summary><pre>${esc(ev.query)}</pre></details>` : "";
  return `<span class="src ${esc(ev.source)}">${esc(SOURCE_LABEL[ev.source] || ev.source)}</span><span class="cite" data-ev="${esc(ev.evidence_id)}">${esc(ev.evidence_id)}</span>${q}`;
}

function metricsLine(ms) {
  if (!ms || !ms.length) return "";
  const m = ms[ms.length - 1];
  const tries = ms.length > 1 ? ` · ${ms.length} attempts (grounding retry)` : "";
  const mode = m.mode === "replay" ? "replay of recorded Nemotron" : "Nemotron live";
  return `<span>${esc(mode)} · ${Math.round(m.latency_ms || 0)} ms${tries}</span>`;
}

function renderEvent(e) {
  const tl = $("#timeline");
  const a = ACTOR[e.actor] || { label: e.actor, cls: "" };
  const d = e.data || {};
  let cls = a.cls, body = "", small = false;
  const meta = (extra = "") => `<div class="meta"><span class="who">${esc(a.label)}</span>${extra}</div>`;

  switch (e.kind) {
    case "incident":
      body = `<div class="body">${esc(d.story)}</div>`; cls = "bad"; break;
    case "detect":
      cls = "bad"; small = true; break;
    case "evidence":
    case "probe":
      body = `<div class="body">${evidenceBody(d.evidence)}${d.requested_by ? ` <span class="muted">requested by ${esc(d.requested_by.replace("_", " "))}</span>` : ""}</div>`;
      cls = "evid"; small = true; break;
    case "candidates":
      body = `<div class="body">${(d.candidates || []).map((c) => `<div>• <b>${esc(c.candidate_id)}</b> — ${esc(c.description)}</div>`).join("")}</div>`;
      small = true; break;
    case "memory":
      body = (d.recalled || []).map((m) => `<div class="mem"><div>${esc(m.content)}</div><div class="m-meta">score ${m.score} · layer ${esc(m.layer)} · confidence ${(+m.confidence).toFixed(2)}</div></div>`).join("");
      cls = "evid"; break;
    case "proposal": {
      const p = d.proposal || {};
      body = `<div class="title">Proposes <b>${esc(p.candidate_id)}</b> <span class="muted">· confidence ${p.confidence ?? "?"}</span></div>
        <div class="body">${esc(p.rationale)}</div>
        ${p.requested_probes && p.requested_probes.length ? `<div class="body muted">Requests probes: ${p.requested_probes.map(esc).join(", ")}</div>` : ""}
        ${p.changes && p.changes.length ? `<div class="body muted">Changes: ${p.changes.map(esc).join("; ")}</div>` : ""}
        ${cites(p.cited_evidence)}`;
      tl.insertAdjacentHTML("beforeend", `<li class="ev ${cls}">${meta(metricsLine(d.metrics))}${body}</li>`);
      return scrollEnd();
    }
    case "review": {
      const r = d.review || {};
      body = `<div class="title"><span class="badge ${esc(r.decision)}">${esc(r.decision)}</span> round ${r.round}</div>
        ${r.objection ? `<div class="body">${esc(r.objection)}</div>` : ""}
        ${r.business_rationale ? `<div class="body"><b>Business:</b> ${esc(r.business_rationale)}</div>` : ""}
        ${r.required_evidence && r.required_evidence.length ? `<div class="body muted">Requires: ${r.required_evidence.map(esc).join(", ")}</div>` : ""}
        ${r.conditions && r.conditions.length ? `<div class="body muted">Conditions: ${r.conditions.map(esc).join("; ")}</div>` : ""}
        ${cites(r.cited_evidence)}`;
      tl.insertAdjacentHTML("beforeend", `<li class="ev ${cls}">${meta(metricsLine(d.metrics))}${body}</li>`);
      return scrollEnd();
    }
    case "override":
    case "grounding":
      body = d.detail ? `<div class="body">${esc(d.detail)}</div>` : ""; cls = "au"; break;
    case "agreement":
      tl.insertAdjacentHTML("beforeend", `<li class="ev divider">${esc(e.title)}</li>`);
      return scrollEnd();
    case "contract":
      body = `<details><summary>Sealed contract · digest ${esc((d.contract?.content_digest || "").slice(0, 12))}…</summary><pre>${esc(JSON.stringify(d.contract, null, 2))}</pre></details>`;
      small = true; break;
    case "authority":
      body = `<ul class="checks">${(d.checks || []).map((c) => `<li class="${c.passed ? "" : "fail"}">${esc(c.name)} <span class="muted">${esc(c.detail)}</span></li>`).join("")}</ul>`;
      cls = d.authorized ? "au" : "bad"; break;
    case "execution":
      cls = "au"; small = true; break;
    case "verification":
    case "truth": {
      const v = d.verification || {};
      body = `<div class="body muted">${esc(v.methodology || "")}</div><ul class="checks">${(v.checks || []).map((c) => `<li class="${c.passed ? "" : "fail"}">${esc(c.name)} <span class="muted">${esc(c.detail)}</span></li>`).join("")}</ul>`;
      cls = v.verified ? "good" : "bad"; break;
    }
    case "adversary":
      cls = "adv"; body = `<div class="body">Original target ${esc(JSON.stringify(d.original_target))} → forged ${esc(JSON.stringify(d.forged_target))}</div>`; break;
    case "escalation":
      cls = "au"; body = briefHtml(d.brief, state.run); break;
    case "memory_write":
      body = (d.stored || []).map((m) => `<div class="mem"><div>${esc(m.content)}</div>${m.supersedes ? `<div class="m-meta">supersedes ${esc(m.supersedes)}</div>` : ""}</div>`).join("")
        + ((d.feedback || []).length ? `<div class="body muted">Feedback: ${d.feedback.map((f) => `${esc(f.id)} → ${esc(f.feedback)}`).join(", ")}</div>` : "");
      cls = "evid"; break;
    case "outcome":
      cls = d.result?.outcome === "VERIFIED_RECOVERED" ? "good" : d.result?.outcome === "FAILED" ? "bad" : "au"; break;
    case "error":
      cls = "bad"; break;
    default:
      small = true;
  }
  tl.insertAdjacentHTML("beforeend", `<li class="ev ${cls} ${small ? "small" : ""}">${meta(`<span>${new Date(e.ts).toLocaleTimeString()}</span>`)}<div class="title">${esc(e.title)}</div>${body}</li>`);
  scrollEnd();
}

function briefHtml(b, run) {
  if (!b) return "";
  const awaiting = run && run.status !== "done";
  return `<div class="body"><b>Owner:</b> ${esc(b.owner_team || "on-call")} ${b.channel ? `(${esc(b.channel)})` : ""}</div>
    <div class="body"><b>What broke:</b> ${esc(b.what_broke)}</div>
    <div class="body"><b>Who is affected:</b> ${esc(b.who_is_affected)}</div>
    ${b.recommendation ? `<div class="body"><b>Guardians' view:</b> ${esc(b.recommendation)}</div>` : ""}
    <div class="options">${(b.options || []).map((o) => `<div class="opt"><div><b>${esc(o.candidate_id)}</b><small>${esc(o.description)}${o.cost ? " · " + esc(o.cost) : ""}</small></div>
      <button class="btn ${o.kind === "TERMINATE" ? "warn" : "neutral"} decide" data-cand="${esc(o.candidate_id)}" ${awaiting ? "" : "hidden"}>Approve</button></div>`).join("")}
      <div class="opt"><div><b>Handle it manually</b><small>Close the run; the owner takes over.</small></div><button class="btn neutral decide" data-cand="" ${awaiting ? "" : "hidden"}>Decline</button></div>
    </div>`;
}

function scrollEnd() {
  const tl = $("#timeline");
  const last = tl.lastElementChild;
  if (last) last.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

document.addEventListener("click", async (ev) => {
  const c = ev.target.closest(".cite");
  if (c) return showEvidence(c.dataset.ev);
  const d = ev.target.closest(".decide");
  if (d && state.run) {
    const cand = d.dataset.cand;
    try {
      await api(`/api/runs/${state.run.run_id}/decision`, {
        method: "POST",
        body: JSON.stringify({ approve: !!cand, candidate_id: cand || null, note: "decided in console" }),
      });
      document.querySelectorAll(".decide").forEach((b) => (b.hidden = true));
      watchRun(state.run.run_id, { ...state.run, status: "running" });
    } catch (e) { alert(e.message); }
  }
  const h = ev.target.closest(".hist");
  if (h) openHistoric(h.dataset.id);
});

function showEvidence(id) {
  const e = state.evidence[id];
  $("#drawer-title").textContent = e ? `${id} · ${SOURCE_LABEL[e.source] || e.source} · ${e.probe}` : id;
  $("#drawer-body").innerHTML = e
    ? `<p>${esc(e.summary)}</p>${e.query ? `<h4>Query</h4><pre>${esc(e.query)}</pre>` : ""}<h4>Facts</h4><pre>${esc(JSON.stringify(e.facts, null, 2))}</pre>
       <p class="muted">Requested by ${esc(e.requested_by)} at ${esc(new Date(e.collected_at).toLocaleTimeString())}</p>`
    : `<p class="muted">Evidence not loaded yet.</p>`;
  $("#drawer").hidden = false;
}
$("#drawer-close").addEventListener("click", () => ($("#drawer").hidden = true));
$("#drawer").addEventListener("click", (e) => { if (e.target.id === "drawer") $("#drawer").hidden = true; });

// ----------------------------------------------------------------- receipt

async function loadReceipt(runId) {
  const run = await api(`/api/runs/${runId}`);
  state.run = run;
  (run.evidence || []).forEach((e) => (state.evidence[e.evidence_id] = e));
  setStatus(run.status);
  const r = run.result || {};
  const act = r.action || {};
  const ver = r.verification || {};
  const events = run.events || [];
  const why = [];
  const firstProp = events.find((e) => e.kind === "proposal");
  const reviews = events.filter((e) => e.kind === "review");
  const auth = events.find((e) => e.kind === "authority");
  if (firstProp) why.push(`Database Guardian opened with <b>${esc(firstProp.data.proposal.candidate_id)}</b>.`);
  reviews.forEach((rv) => why.push(`Continuity Guardian: <b>${esc(rv.data.review.decision)}</b> ${esc((rv.data.review.objection || rv.data.review.business_rationale || "").slice(0, 160))}`));
  events.filter((e) => e.kind === "override").forEach((o) => why.push(`Invariant override: ${esc(o.data.detail.slice(0, 140))}`));
  if (auth) why.push(`Authority: ${esc(auth.title)}`);
  if (ver.checks) why.push(`Verification: ${ver.checks.map((c) => `${c.passed ? "✓" : "✗"} ${esc(c.name)}`).join(", ")}`);
  const report = r.audit ? `<h4>Recovery Auditor report</h4><div class="body">${esc(r.audit.report)}</div>
     ${(r.audit.lessons || []).length ? `<h4>Lessons stored in H-MEM</h4><ul>${r.audit.lessons.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : ""}` : "";
  $("#tab-receipt").innerHTML = `<div class="receipt">
      <span class="outcome ${esc(r.outcome)}">${esc((r.outcome || run.status).replace("_", " "))}</span>
      ${r.correct === false ? `<span class="badge fail">differs from expected (${esc(r.expected_outcome)})</span>` : r.correct ? `<span class="badge ok">matches expected</span>` : ""}
      <dl class="kv">
        <dt>Action</dt><dd>${esc(act.kind || "–")}${act.target ? ` → ${esc(act.target.application_name)} (pid ${esc(act.target.pid)})` : ""}${act.executed === false ? " (not executed)" : ""}</dd>
        <dt>Time</dt><dd>${esc(r.duration_s)} s</dd>
        <dt>Lost checkouts</dt><dd>${esc(r.lost_checkouts ?? "–")}${r.revenue_lost_usd != null ? ` (~$${esc(Number(r.revenue_lost_usd).toLocaleString())})` : ""}</dd>
        <dt>Settlements aborted</dt><dd>${esc(r.settlements_aborted ?? "–")}</dd>
        <dt>Rounds</dt><dd>${esc(r.rounds)}</dd>
        <dt>Model calls</dt><dd>${esc(r.model_calls)} (${esc(run.model)} · ${esc(run.inference_mode)})</dd>
        <dt>Business data</dt><dd>${esc(run.zetaris_mode)}</dd>
        <dt>Memories used</dt><dd>${esc(r.recalled_memories)}</dd>
        <dt>Unsafe action</dt><dd>${r.unsafe_action ? "YES" : "no"}</dd>
        <dt>Business harm</dt><dd>${r.business_harm ? "YES" : "no"}</dd>
        <dt>False recovery claim</dt><dd>${r.false_recovery_claim ? "YES" : "no"}</dd>
      </dl>
      <h4>Why</h4><ol class="why">${why.map((w) => `<li>${w}</li>`).join("")}</ol>
      ${report}
      ${r.brief && run.status === "awaiting_human" ? `<h4>Decision needed</h4>${briefHtml(r.brief, run)}` : ""}
      <details><summary>Raw run JSON</summary><pre>${esc(JSON.stringify(r, null, 2))}</pre></details>
    </div>`;
}

// ------------------------------------------------------------------ memory

async function refreshMemory() {
  try {
    const m = await api("/api/memory");
    $("#tab-memory").innerHTML = `<p class="muted">Embedder: ${esc(m.embedder)} · ${m.memories.length} memories · ledger is append-only.</p>`
      + (m.memories.length ? m.memories.map((x) => `<div class="mem ${x.superseded_by ? "superseded" : ""}"><div>${esc(x.content)}</div>
        <div class="m-meta">${esc(x.layer)} · confidence ${(+x.confidence).toFixed(2)} · recalled ${x.access_count}× ${x.superseded_by ? "· SUPERSEDED" : ""}</div></div>`).join("") : `<p class="muted">Empty. Memories are written after verification.</p>`)
      + `<details><summary>Trust ledger (latest ${m.ledger.length})</summary><pre>${esc(m.ledger.map((l) => `${new Date(l.ts * 1000).toLocaleTimeString()} ${l.action} ${l.memory_id}`).join("\n"))}</pre></details>`;
  } catch (e) { /* ignore */ }
}

// ------------------------------------------------------------------- evals

async function refreshEvals() {
  try {
    const all = await api("/api/evals");
    const labels = Object.keys(all);
    if (!labels.length) { $("#tab-evals").innerHTML = `<p class="muted">No eval results yet. Run <code>python -m app.evals.run</code>.</p>`; return; }
    $("#tab-evals").innerHTML = labels.map((l) => {
      const s = all[l];
      const rows = Object.entries(s.aggregate || {}).map(([arch, a]) => `<tr><td>${esc(arch)}</td><td class="num">${a.correct}/${a.runs}</td><td class="num">${a.unsafe_actions}</td><td class="num">${a.business_harm}</td><td class="num">${a.false_recovery_claims}</td><td class="num">${a.verified_recoveries}</td></tr>`).join("");
      return `<h4>${esc(l)} <span class="muted">· ${esc(s.model)} · ${esc(s.zetaris_mode)}</span></h4>
        <table><thead><tr><th>Arm</th><th>Correct</th><th>Unsafe</th><th>Harm</th><th>False claim</th><th>Verified</th></tr></thead><tbody>${rows}</tbody></table>
        ${(s.encores || []).length ? `<p class="muted">${s.encores.map(esc).join("<br>")}</p>` : ""}`;
    }).join("");
  } catch (e) { /* ignore */ }
}

async function refreshHistory() {
  try {
    const runs = await api("/api/runs");
    $("#tab-history").innerHTML = runs.length ? runs.map((r) => `<div class="hist" data-id="${esc(r.run_id)}"><span>${esc(r.scenario.split("_")[0])} · ${esc(r.arch)}</span><span>${esc(r.result?.outcome || r.status)}</span></div>`).join("") : `<p class="muted">No runs yet.</p>`;
  } catch (e) { /* ignore */ }
}

async function openHistoric(id) {
  const run = await api(`/api/runs/${id}`);
  if (state.source) state.source.close();
  state.run = run;
  $("#timeline").innerHTML = "";
  (run.evidence || []).forEach((e) => (state.evidence[e.evidence_id] = e));
  $("#tl-title").textContent = `${run.title || run.scenario} · ${run.arch}`;
  (run.events || []).forEach(renderEvent);
  if (run.status === "running") watchRun(id, run); else loadReceipt(id);
  selectTab("receipt");
}

// ---------------------------------------------------------------- wiring

function selectTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".tabpane").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`));
}
document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
  selectTab(t.dataset.tab);
  if (t.dataset.tab === "memory") refreshMemory();
  if (t.dataset.tab === "evals") refreshEvals();
  if (t.dataset.tab === "history") refreshHistory();
}));
$("#btn-reset").addEventListener("click", () => api("/api/reset", { method: "POST" }).catch((e) => alert(e.message)));
$("#btn-clear-mem").addEventListener("click", async () => {
  if (!confirm("Clear all Meterless memories? The next run starts cold.")) return;
  await api("/api/memory/clear", { method: "POST" }).catch((e) => alert(e.message));
  refreshMemory(); refreshStatus();
});

(async function init() {
  await loadScenarios();
  refreshStatus(); refreshSpark(); refreshMemory(); refreshEvals(); refreshHistory();
  setInterval(refreshStatus, 2000);
  setInterval(refreshSpark, 2000);
  const runs = await api("/api/runs").catch(() => []);
  const live = runs.find((r) => r.status === "running" || r.status === "awaiting_human");
  if (live) openHistoric(live.run_id);
})();
