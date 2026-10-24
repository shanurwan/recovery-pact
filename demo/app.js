// RecoveryPact replay page. Plays recorded benchmark traces side by side. No build step.
"use strict";

const REPO = "https://github.com/shanurwan/recovery-pact/blob/main/";
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const nemotronName = (m) => {
  const x = /nemotron-([\d.]+)-([a-z]+)/.exec(m || "");
  return x ? `Nemotron ${x[1]} ${x[2][0].toUpperCase()}${x[2].slice(1)}` : (m || "").replace("nvidia/", "");
};
// A verified Meterless Nightshift receipt for this model answer.
const sigBadge = (e) => e.signed ? ` <span class="sig" title="Meterless Nightshift receipt: Ed25519 signature verified (key ${esc(e.signed.key)}); the prompt went to: ${esc(e.signed.egress)}">✓ signed · ${esc(nemotronName(e.signed.winner))}</span>` : "";

const SIDES = {
  naive_single: { name: "Typical AI agent", short: "Typical agent", sub: "One AI with database access fixes it on its own." },
  gated_single: { name: "AI agent + safety rules", short: "Agent + rules", sub: "One AI, the same safety authority, checks only the database." },
  pact: { name: "RecoveryPact", short: "RecoveryPact", sub: "Database AI and Business AI negotiate; a safety authority decides; the business defines “fixed”." },
};
const WHO_CLASS = {
  database_guardian: "db", solo_agent: "db", continuity_guardian: "biz", recovery_auditor: "biz",
  zetaris: "biz", business_calculator: "biz", authority: "gate", grounding_check: "gate",
  verifier: "gate", eval_judge: "gate", simulator: "bad", detector: "bad", executor: "gate", injection_guard: "gate",
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
  renderHeadline();
  const per = state.index.per_scenario || {};
  const tabs = $("#tabs");
  tabs.setAttribute("role", "tablist");
  tabs.innerHTML = state.index.scenarios
    .map((s) => {
      const p = per[s.id] || {};
      const them = p.naive_single ?? "–";
      return `<button class="tab" type="button" role="tab" data-id="${esc(s.id)}">
        <span class="t-title">${esc(s.title)}</span>
        <span class="t-score"><span class="chip ${them.startsWith("0") ? "bad" : "good"}">${them.startsWith("0") ? "✗" : "✓"} ${esc(SIDES.naive_single.short)} ${esc(them)}</span>
        <span class="chip good">✓ RecoveryPact ${esc(p.pact ?? "–")}</span></span></button>`;
    })
    .join("");
  tabs.addEventListener("click", (e) => {
    const b = e.target.closest(".tab");
    if (b) select(b.dataset.id);
  });
  renderScoreboard();
  const hash = location.hash.slice(1);
  const first = state.index.scenarios.find((s) => hash.length <= 2 && s.id.startsWith(hash.toUpperCase()) && hash) || state.index.scenarios[0];
  select(first.id, false);
}

// Incident B's card settlement (see build_demo.py): each one aborted puts $12,500 at risk.
const SETTLEMENT_USD = 12500;
const usd = (n) => "$" + n.toLocaleString("en-US");

function renderHeadline() {
  const a = state.index.aggregate;
  const us = a.pact, naive = a.naive_single || {}, gated = a.gated_single || {};
  const stat = (big, what, them) => `<div class="hstat glass"><span class="big">${big}</span><span class="what">${what}</span><span class="them">${them}</span></div>`;
  $("#headline-stats").innerHTML = [
    stat(`${us.correct}/${us.runs}`, "right calls", `Typical AI agent: <b>${naive.correct}/${naive.runs}</b>`),
    stat(us.unsafe_actions, "unsafe actions", `Typical AI agent: <b>${naive.unsafe_actions}</b>`),
    stat(usd((us.settlements_aborted ?? 0) * SETTLEMENT_USD), "of card settlements put at risk",
         `Typical AI agent: <b>${naive.settlements_aborted == null ? "–" : `${usd(naive.settlements_aborted * SETTLEMENT_USD)} (${naive.settlements_aborted} × ${usd(SETTLEMENT_USD)})`}</b>`),
    stat(us.false_recovery_claims, "false “fixed” claims", `Agent + safety rules: <b>${gated.false_recovery_claims ?? "–"}</b> · Typical: <b>${naive.false_recovery_claims}</b>`),
  ].join("");
}

async function select(id, scroll = true) {
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
  await loadSides();
  if (scroll) $("#story").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function loadSides() {
  const sc = state.scenario;
  const [l, r] = await Promise.all([loadJSON(`data/${sc.id}--${state.left}.json`), loadJSON(`data/${sc.id}--pact.json`)]);
  state.data = { left: l, right: r };
  state.clock = Infinity; // complete at rest: everything visible until Replay is pressed
  render();
  setScene(1);
}

function sideHtml(d, key) {
  const meta = SIDES[d.arch];
  return `<div class="side-head"><span class="name">${esc(meta.name)}</span><span class="sub">${esc(meta.sub)}</span>
      <span class="prov">Recorded ${esc(new Date(d.started_at).toUTCString())} · ${esc((d.model || "").replace("nvidia/", ""))} · ${esc(d.run_id)} ·
      <a href="${REPO + esc(d.source_file)}" target="_blank" rel="noopener">raw trace</a></span></div>
    <div class="chart"><svg id="chart-${key}" viewBox="0 0 600 86" preserveAspectRatio="none" role="img" aria-label="Checkouts per second during this run: green succeeded, red failed"></svg>
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
          <span class="who ${WHO_CLASS[e.actor] || ""}">${esc(e.who)}</span> ${esc(e.caption)}${sigBadge(e)}
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

function series(d) {
  const span = Math.ceil(Math.max(horizon(), 1));
  const ok = new Array(span + 1).fill(0), bad = new Array(span + 1).fill(0);
  for (const [t, o, b] of d.pulse) {
    if (t >= 0 && t <= span) { ok[t] += o; bad[t] += b; }
  }
  return { span, ok, bad };
}

function drawChart(d, key) {
  const svg = $(`#chart-${key}`);
  const W = 600, H = 86, pad = 4;
  const { span, ok, bad } = series(d);
  const max = Math.max(4, ...ok.map((o, i) => o + bad[i]));
  const x = (i) => (i / span) * W;
  const y = (v) => H - pad - (v / max) * (H - pad * 2);
  const area = (top, base) => {
    let p = `M0,${y(base[0])}`;
    for (let i = 0; i <= span; i++) p += ` L${x(i).toFixed(1)},${y(top[i]).toFixed(1)}`;
    for (let i = span; i >= 0; i--) p += ` L${x(i).toFixed(1)},${y(base[i]).toFixed(1)}`;
    return p + "Z";
  };
  const zero = ok.map(() => 0);
  const stack = ok.map((o, i) => o + bad[i]);
  const cut = Number.isFinite(state.clock) ? Math.min(W, (state.clock / span) * W) : W;
  let okSum = 0, badSum = 0;
  for (let i = 0; i <= span; i++) if (i <= state.clock) { okSum += ok[i]; badSum += bad[i]; }
  const id = `c-${key}`;
  svg.innerHTML = `<defs>
      <linearGradient id="${id}-ok" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--biz)" stop-opacity=".9"/><stop offset="1" stop-color="var(--biz)" stop-opacity=".15"/></linearGradient>
      <linearGradient id="${id}-bad" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--bad)" stop-opacity=".95"/><stop offset="1" stop-color="var(--bad)" stop-opacity=".35"/></linearGradient>
      <clipPath id="${id}-clip"><rect x="0" y="0" width="${cut}" height="${H}"/></clipPath>
    </defs>
    <g opacity=".16"><path d="${area(ok, zero)}" fill="var(--biz)"/><path d="${area(stack, ok)}" fill="var(--bad)"/></g>
    <g clip-path="url(#${id}-clip)"><path d="${area(ok, zero)}" fill="url(#${id}-ok)"/><path d="${area(stack, ok)}" fill="url(#${id}-bad)"/></g>
    ${Number.isFinite(state.clock) ? `<line x1="${cut}" x2="${cut}" y1="0" y2="${H}" stroke="var(--ink)" stroke-width="1.5" opacity=".8"/>` : ""}`;
  $(`#cnt-${key}`).textContent = `${okSum} ok · ${badSum} failed`;
}

// The 3D scene follows RecoveryPact's real checkout health during a replay.
function setScene(h) {
  if (window.rpScene) window.rpScene.setHealth(h);
}
function sceneHealthAt(clock) {
  const { ok, bad } = series(state.data.right);
  const t = Math.floor(clock);
  let o = 0, b = 0;
  for (let i = Math.max(0, t - 2); i <= t && i < ok.length; i++) { o += ok[i]; b += bad[i]; }
  return o + b ? o / (o + b) : 1;
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
    if (state.clock >= end) { state.clock = Infinity; stop(); draw(); setScene(1); return; }
    draw();
    setScene(sceneHealthAt(state.clock));
    state.raf = requestAnimationFrame(tick);
  };
  state.raf = requestAnimationFrame(tick);
}

function stop() {
  cancelAnimationFrame(state.raf);
  state.playing = false;
  $("#play").textContent = "▶ Replay both";
}

$("#play").addEventListener("click", () => {
  if (state.playing) { stop(); state.clock = Infinity; draw(); setScene(1); } else play();
});
$("#tech").addEventListener("change", () => document.querySelectorAll(".feed .tech").forEach((el) => (el.hidden = !$("#tech").checked)));

function renderScoreboard() {
  const ix = state.index;
  const a = ix.aggregate;
  const us = a.pact, arms = Object.keys(a).filter((k) => k !== "pact");
  const row = (label, key) => `<div class="score glass"><span class="label">${label}</span>
      <div class="row us"><span>RecoveryPact</span><b>${us[key]}</b></div>
      ${arms.map((k) => `<div class="row them"><span>${esc(SIDES[k].name)}</span><b>${a[k][key]}</b></div>`).join("")}</div>`;
  const per = ix.per_scenario || {};
  const cell = (v) => `<td class="num ${v && v.startsWith("0") ? "zero" : v && v.split("/")[0] === v.split("/")[1] ? "full" : ""}">${esc(v ?? "–")}</td>`;
  $("#scoreboard").innerHTML = `<h2>Across every incident</h2>
    <p class="small">${esc(ix.repeats)} independent repeat(s) of all ${Object.keys(per).length} incidents, ${esc((ix.model || "").replace("nvidia/", ""))}, business records via ${ix.zetaris_mode === "zetaris" ? "live Zetaris" : "local fallback"}. Recomputed from raw traces by the validator.</p>
    <div class="score-grid">
      ${row("Right call", "correct")}
      ${row("Unsafe actions (stopped something it must not)", "unsafe_actions")}
      ${row("Business harm (did what the business ruled out)", "business_harm")}
      ${row("Claimed “fixed” while checkout was still broken", "false_recovery_claims")}
    </div>
    <div class="table-box glass"><table><thead><tr><th>Incident</th><th>RecoveryPact</th>${arms.map((k) => `<th>${esc(SIDES[k].name)}</th>`).join("")}</tr></thead><tbody>
      ${ix.scenarios.map((s) => `<tr><td>${esc(s.title)}</td>${cell(per[s.id]?.pact)}${arms.map((k) => cell(per[s.id]?.[k])).join("")}</tr>`).join("")}
    </tbody></table></div>
    <p class="small">Correct out of runs. “${esc(SIDES.pact.name)}” counts are out of ${esc(us.runs)} runs.</p>`;
}

init();
