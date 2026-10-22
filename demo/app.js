// RecoveryPact replay page. Plays recorded benchmark traces side by side. No build step.
"use strict";

const REPO = "https://github.com/shanurwan/recovery-pact/blob/main/";
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const SIDES = {
  naive_single: { name: "Typical AI agent", sub: "One AI with database access fixes it on its own." },
  gated_single: { name: "AI agent + safety rules", sub: "One AI, the same safety authority, checks only the database." },
  pact: { name: "RecoveryPact", sub: "Database AI and Business AI negotiate; a safety authority decides; the business defines “fixed”." },
};
const WHO_CLASS = {
  database_guardian: "db", solo_agent: "db", continuity_guardian: "biz", recovery_auditor: "biz",
  zetaris: "biz", business_calculator: "biz", authority: "gate", grounding_check: "gate",
  verifier: "gate", eval_judge: "gate", simulator: "bad", detector: "bad", executor: "gate",
};

const state = { index: null, scenario: null, left: "naive_single", data: {}, clock: Infinity, playing: false, raf: 0 };

async function loadJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

async function init() {
  try {
    state.index = await loadJSON("data/index.json");
  } catch (e) {
    $("#story").innerHTML = `<p>Replay data is missing. Build it with <code>python -m app.evals.build_demo</code>.</p>`;
    return;
  }
  const tabs = $("#tabs");
  tabs.innerHTML = state.index.scenarios
    .map((s) => `<button class="tab" type="button" role="tab" data-id="${esc(s.id)}">${esc(s.title)}</button>`)
    .join("");
  tabs.addEventListener("click", (e) => {
    const b = e.target.closest(".tab");
    if (b) select(b.dataset.id);
  });
  renderScoreboard();
  const hash = location.hash.slice(1);
  const first = state.index.scenarios.find((s) => s.id.startsWith(hash.toUpperCase())) || state.index.scenarios[0];
  select(first.id);
}

async function select(id) {
  stop();
  state.scenario = state.index.scenarios.find((s) => s.id === id);
  document.querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-selected", String(t.dataset.id === id)));
  try { history.replaceState(null, "", "#" + id.split("_")[0].toLowerCase()); } catch (e) { /* sandboxed */ }
  const sc = state.scenario;
  const right = { TERMINATE: "stop the job safely and confirm checkout is back", WAIT: "wait: it finishes inside what the business tolerates, and stopping it would harm customers",
                  ESCALATE: "hand the decision to the owning team, with the costs of each option", NONE: "refuse the tampered plan" }[sc.expected_action];
  const leftChoices = sc.arms.filter((a) => a !== "pact");
  $("#story").innerHTML = `<span class="title">${esc(sc.title)}</span><p>${esc(sc.story)}</p>
    <p class="right">The right call: <b>${esc(right)}</b>.</p>
    ${leftChoices.length > 1 ? `<label class="small">Compare RecoveryPact with
      <select id="leftpick">${leftChoices.map((a) => `<option value="${a}" ${a === state.left ? "selected" : ""}>${esc(SIDES[a].name)}</option>`).join("")}</select></label>` : ""}`;
  const pick = $("#leftpick");
  if (pick) pick.addEventListener("change", () => { state.left = pick.value; loadSides(); });
  if (!leftChoices.includes(state.left)) state.left = leftChoices[0];
  loadSides();
}

async function loadSides() {
  const sc = state.scenario;
  const [l, r] = await Promise.all([loadJSON(`data/${sc.id}--${state.left}.json`), loadJSON(`data/${sc.id}--pact.json`)]);
  state.data = { left: l, right: r };
  state.clock = Infinity; // complete at rest: everything visible until Replay is pressed
  render();
}

function sideHtml(d, key) {
  const meta = SIDES[d.arch];
  return `<div class="side-head"><span class="name">${esc(meta.name)}</span><span class="sub">${esc(meta.sub)}</span>
      <span class="prov">Recorded ${esc(new Date(d.started_at).toUTCString())} · ${esc((d.model || "").replace("nvidia/", ""))} · ${esc(d.run_id)} ·
      <a href="${REPO + esc(d.source_file)}" target="_blank" rel="noopener">raw trace</a></span></div>
    <div class="chart"><svg id="chart-${key}" viewBox="0 0 600 70" preserveAspectRatio="none" role="img" aria-label="Checkouts per second during this run: green succeeded, red failed"></svg>
      <div class="legend"><span>checkouts per second</span><span id="cnt-${key}"></span></div></div>
    <ol class="feed" id="feed-${key}"></ol>
    <div id="verdict-${key}"></div>`;
}

function render() {
  $("#side-naive").innerHTML = sideHtml(state.data.left, "left");
  $("#side-pact").innerHTML = sideHtml(state.data.right, "right");
  draw();
}

function horizon() {
  const last = (d) => Math.max(d.events.at(-1)?.t || 0, d.pulse.at(-1)?.[0] || 0);
  return Math.max(last(state.data.left), last(state.data.right));
}

function draw() {
  for (const key of ["left", "right"]) {
    const d = state.data[key];
    drawChart(d, key);
    const feed = $(`#feed-${key}`);
    const shown = d.events.filter((e) => e.caption && e.t <= state.clock);
    if (feed.childElementCount !== shown.length) {
      const tech = $("#tech").checked;
      feed.innerHTML = shown.map((e) => `<li><span class="ts">${e.t.toFixed(0)} s</span><div>
          <span class="who ${WHO_CLASS[e.actor] || ""}">${esc(e.who)}</span> ${esc(e.caption)}
          <div class="tech" ${tech ? "" : "hidden"}>${esc(techText(e))}</div></div></li>`).join("");
      if (state.playing) feed.scrollTop = feed.scrollHeight;
    }
    const done = state.clock >= (d.events.at(-1)?.t || 0);
    const v = d.verdict;
    $(`#verdict-${key}`).innerHTML = done
      ? `<div class="verdict ${v.ok ? "good" : "bad"}"><span class="v-title">${v.ok ? "✓ Right call" : "✗ Wrong call"}</span>
          ${v.lines.map((l) => `<p>${esc(l)}</p>`).join("")}
          <span class="v-stats">${esc(v.duration_s)} s · ${esc(v.lost_checkouts ?? "–")} failed checkouts during the incident</span></div>`
      : `<div class="verdict pending">In progress…</div>`;
  }
  $("#clock").textContent = Number.isFinite(state.clock) ? `${Math.floor(state.clock)} s` : `${Math.round(horizon())} s total`;
}

function techText(e) {
  const t = e.tech || {};
  const parts = [t.title];
  if (t.detail) parts.push(JSON.stringify(t.detail, null, 1).replace(/[{}"]/g, "").trim());
  if (t.model && t.model.latency_ms != null) parts.push(`model call ${Math.round(t.model.latency_ms)} ms (${t.model.mode})`);
  return parts.filter(Boolean).join("\n");
}

function drawChart(d, key) {
  const svg = $(`#chart-${key}`);
  const W = 600, H = 70;
  const span = Math.max(horizon(), 1);
  const max = Math.max(4, ...d.pulse.map((p) => p[1] + p[2]));
  const bw = Math.max(1, W / span - 0.5);
  let out = "", ok = 0, bad = 0;
  for (const [t, o, b] of d.pulse) {
    const x = (t / span) * W;
    const live = t <= state.clock;
    const op = live ? 1 : 0.18;
    if (live) { ok += o; bad += b; }
    const ho = (o / max) * H, hb = (b / max) * H;
    if (o) out += `<rect x="${x.toFixed(1)}" y="${(H - ho).toFixed(1)}" width="${bw.toFixed(1)}" height="${ho.toFixed(1)}" fill="var(--chart-ok)" opacity="${op}"/>`;
    if (b) out += `<rect x="${x.toFixed(1)}" y="${(H - ho - hb).toFixed(1)}" width="${bw.toFixed(1)}" height="${hb.toFixed(1)}" fill="var(--chart-bad)" opacity="${op}"/>`;
  }
  if (Number.isFinite(state.clock)) {
    const cx = Math.min(W, (state.clock / span) * W);
    out += `<line x1="${cx}" x2="${cx}" y1="0" y2="${H}" stroke="var(--ink)" stroke-width="1.5"/>`;
  }
  svg.innerHTML = out;
  $(`#cnt-${key}`).textContent = `${ok} ok · ${bad} failed`;
}

function play() {
  stop();
  state.playing = true;
  const speed = Number($("#speed").value);
  const end = horizon();
  const t0 = performance.now();
  state.clock = 0;
  $("#play").textContent = "■ Stop";
  const tick = (now) => {
    state.clock = ((now - t0) / 1000) * speed;
    if (state.clock >= end) { state.clock = Infinity; stop(); draw(); return; }
    draw();
    state.raf = requestAnimationFrame(tick);
  };
  state.raf = requestAnimationFrame(tick);
}

function stop() {
  cancelAnimationFrame(state.raf);
  state.playing = false;
  $("#play").textContent = "▶ Replay both";
}

$("#play").addEventListener("click", () => (state.playing ? (stop(), (state.clock = Infinity), draw()) : play()));
$("#tech").addEventListener("change", () => document.querySelectorAll(".feed .tech").forEach((el) => (el.hidden = !$("#tech").checked)));

function renderScoreboard() {
  const ix = state.index;
  const a = ix.aggregate;
  const us = a.pact, arms = Object.keys(a).filter((k) => k !== "pact");
  const row = (label, key, good) => `<div class="score"><span class="label">${label}</span>
      <div class="row us"><span>RecoveryPact</span><b>${us[key]}</b></div>
      ${arms.map((k) => `<div class="row them"><span>${esc(SIDES[k].name)}</span><b>${a[k][key]}</b></div>`).join("")}</div>`;
  const per = ix.per_scenario || {};
  $("#scoreboard").innerHTML = `<h2>Across every incident</h2>
    <p class="small">${esc(ix.repeats)} independent repeat(s) of all ${Object.keys(per).length} incidents, ${esc((ix.model || "").replace("nvidia/", ""))}, business records via ${ix.zetaris_mode === "zetaris" ? "live Zetaris" : "local fallback"}. Recomputed from raw traces by the validator.</p>
    <div class="score-grid">
      ${row("Right call", "correct")}
      ${row("Unsafe actions (stopped something it must not)", "unsafe_actions")}
      ${row("Business harm (did what the business ruled out)", "business_harm")}
      ${row("Claimed “fixed” while checkout was still broken", "false_recovery_claims")}
    </div>
    <div class="table-box"><table><thead><tr><th>Incident</th><th>RecoveryPact</th>${arms.map((k) => `<th>${esc(SIDES[k].name)}</th>`).join("")}</tr></thead><tbody>
      ${ix.scenarios.map((s) => `<tr><td>${esc(s.title)}</td><td class="num">${esc(per[s.id]?.pact ?? "–")}</td>${arms.map((k) => `<td class="num">${esc(per[s.id]?.[k] ?? "–")}</td>`).join("")}</tr>`).join("")}
    </tbody></table></div>
    <p class="small">Correct out of runs. “${esc(SIDES.pact.name)}” counts are out of ${esc(us.runs)} runs.</p>`;
}

init();
