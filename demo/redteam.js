// "Try to break it": pick an attack, replay the recorded run of RecoveryPact under it.
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
const NAMES = { naive_single: "Typical AI agent, same attack", pact: "RecoveryPact" };
const WHO_CLASS = {
  database_guardian: "db", solo_agent: "db", continuity_guardian: "biz", recovery_auditor: "biz",
  zetaris: "biz", business_calculator: "biz", authority: "gate", grounding_check: "gate", meterless_hmem: "mem",
  verifier: "gate", eval_judge: "gate", simulator: "bad", detector: "bad", executor: "gate", injection_guard: "gate",
};
const state = { attack: null, clock: Infinity, playing: false, raf: 0 };

async function loadJSON(p) {
  const r = await fetch(p);
  if (!r.ok) throw new Error(`${p}: ${r.status}`);
  return r.json();
}

async function init() {
  const ix = await loadJSON("data/redteam/index.json");
  const t = ix.totals;
  const stat = (big, what, sub) => `<div class="hstat glass"><span class="big">${big}</span><span class="what">${what}</span><span class="them">${sub}</span></div>`;
  $("#rt-stats").innerHTML = [
    stat(t.runs, "attacked runs", "seven attacks, all recorded"),
    stat(t.unsafe, "unsafe actions", "nothing protected was stopped"),
    stat(t.harm, "business harm", "no owner's rule was broken"),
    stat(t.false_claims, "false “fixed” claims", "never declared victory early"),
  ].join("");
  $("#attacks").innerHTML = ix.attacks.map((a) => `<button class="atk glass" type="button" data-id="${esc(a.id)}">
      <span class="atk-title">${esc(a.title)}</span><span class="atk-goal">${esc(a.goal)}</span>
      <span class="chip good">✓ 0 unsafe in ${esc(a.tally.runs)} run${a.tally.runs === 1 ? "" : "s"}</span></button>`).join("");
  $("#attacks").addEventListener("click", (e) => {
    const b = e.target.closest(".atk");
    if (b) select(b.dataset.id, true);
  });
  const want = location.hash.slice(1);
  select(ix.attacks.some((a) => a.id === want) ? want : ix.attacks[0].id, false);
}

async function select(id, scroll) {
  stop();
  document.querySelectorAll(".atk").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.id === id)));
  try { history.replaceState(null, "", "#" + id); } catch (e) { /* sandboxed */ }
  const a = (state.attack = await loadJSON(`data/redteam/${id}.json`));
  $("#brief").innerHTML = `<span class="eyebrow rt-eyebrow">Your attack</span><span class="title">${esc(a.title)}</span>
    <p>${esc(a.attempt)}</p><p class="right">You want: <b>${esc(a.goal)}</b></p>`;
  const two = a.sides.length > 1;
  $("#rt-arena").className = "arena" + (two ? "" : " solo");
  $("#rt-arena").innerHTML = a.sides.map((s, i) => `${i ? '<div class="vs" aria-hidden="true"><span>VS</span></div>' : ""}
    <article class="side ${s.arch === "pact" ? "pact" : "naive"} glass">${sideHtml(s, i)}</article>`).join("")
    + (two ? "" : `<p class="small solo-note">This attack targets RecoveryPact's own memory or business sources, so there is no single-agent run to compare.</p>`);
  state.clock = Infinity;
  draw();
  if (scroll) $("#brief").scrollIntoView({ behavior: "smooth", block: "start" });
}

function sideHtml(d, i) {
  return `<div class="side-head"><span class="name">${esc(NAMES[d.arch] || d.arch)}</span>
      <span class="prov">Recorded ${esc(new Date(d.started_at).toUTCString())} · ${esc((d.model || "").replace("nvidia/", ""))} · ${esc(d.run_id)} ·
      <a href="${REPO + esc(d.source_file)}" target="_blank" rel="noopener">raw trace</a></span></div>
    <div class="chart"><svg id="chart-${i}" viewBox="0 0 600 86" preserveAspectRatio="none" role="img" aria-label="Checkouts per second: green succeeded, red failed"></svg>
      <div class="legend"><span>checkouts per second</span><span id="cnt-${i}"></span></div></div>
    <ol class="feed" id="feed-${i}"></ol><div id="verdict-${i}"></div>`;
}

function horizon() {
  return Math.max(...state.attack.sides.map((d) => Math.max(d.events.at(-1)?.t || 0, d.pulse.at(-1)?.[0] || 0)));
}

function draw() {
  const a = state.attack;
  a.sides.forEach((d, i) => {
    drawChart(d, i);
    const shown = d.events.filter((e) => e.caption && e.t <= state.clock);
    const feed = $(`#feed-${i}`);
    if (feed.childElementCount !== shown.length) {
      feed.innerHTML = shown.map((e) => `<li><span class="ts">${e.t.toFixed(0)} s</span><div>
        <span class="who ${WHO_CLASS[e.actor] || ""}">${esc(e.who)}</span> ${esc(e.caption)}${sigBadge(e)}</div></li>`).join("");
      if (state.playing) feed.scrollTop = feed.scrollHeight;
    }
    const done = state.clock >= (d.events.at(-1)?.t || 0);
    const v = d.verdict;
    const pact = d.arch === "pact";
    $(`#verdict-${i}`).innerHTML = !done ? `<div class="verdict pending">Attack in progress…</div>`
      : pact ? `<div class="verdict good"><span class="v-title">✓ ${esc(a.result)}</span>${a.lines.map((l) => `<p>${esc(l)}</p>`).join("")}
          <span class="v-stats">0 unsafe actions in all ${esc(a.tally.runs)} recorded runs of this attack · ${esc(v.duration_s)} s</span></div>`
      : `<div class="verdict bad"><span class="v-title">✗ The attack worked</span>${v.lines.map((l) => `<p>${esc(l)}</p>`).join("")}
          <span class="v-stats">${esc(v.duration_s)} s</span></div>`;
  });
  $("#rt-clock").textContent = Number.isFinite(state.clock) ? `${Math.floor(state.clock)} s` : `${Math.round(horizon())} s total`;
}

function series(d) {
  const span = Math.ceil(Math.max(horizon(), 1));
  const ok = new Array(span + 1).fill(0), bad = new Array(span + 1).fill(0);
  for (const [t, o, b] of d.pulse) if (t >= 0 && t <= span) { ok[t] += o; bad[t] += b; }
  return { span, ok, bad };
}

function drawChart(d, i) {
  const svg = $(`#chart-${i}`);
  const W = 600, H = 86, pad = 4;
  const { span, ok, bad } = series(d);
  const max = Math.max(4, ...ok.map((o, k) => o + bad[k]));
  const x = (k) => (k / span) * W, y = (v) => H - pad - (v / max) * (H - pad * 2);
  const area = (top, base) => {
    let p = `M0,${y(base[0])}`;
    for (let k = 0; k <= span; k++) p += ` L${x(k).toFixed(1)},${y(top[k]).toFixed(1)}`;
    for (let k = span; k >= 0; k--) p += ` L${x(k).toFixed(1)},${y(base[k]).toFixed(1)}`;
    return p + "Z";
  };
  const zero = ok.map(() => 0), stack = ok.map((o, k) => o + bad[k]);
  const cut = Number.isFinite(state.clock) ? Math.min(W, (state.clock / span) * W) : W;
  let okSum = 0, badSum = 0;
  for (let k = 0; k <= span; k++) if (k <= state.clock) { okSum += ok[k]; badSum += bad[k]; }
  svg.innerHTML = `<defs><clipPath id="rc-${i}"><rect x="0" y="0" width="${cut}" height="${H}"/></clipPath></defs>
    <g opacity=".16"><path d="${area(ok, zero)}" fill="var(--biz)"/><path d="${area(stack, ok)}" fill="var(--bad)"/></g>
    <g clip-path="url(#rc-${i})"><path d="${area(ok, zero)}" fill="var(--biz)" opacity=".75"/><path d="${area(stack, ok)}" fill="var(--bad)" opacity=".85"/></g>
    ${Number.isFinite(state.clock) ? `<line x1="${cut}" x2="${cut}" y1="0" y2="${H}" stroke="var(--ink)" stroke-width="1.5" opacity=".8"/>` : ""}`;
  $(`#cnt-${i}`).textContent = `${okSum} ok · ${badSum} failed`;
}

function play() {
  stop();
  state.playing = true;
  const speed = Number($("#rt-speed").value), end = horizon(), t0 = performance.now();
  state.clock = 0;
  $("#rt-play").textContent = "■ Stop";
  const tick = (now) => {
    state.clock = ((now - t0) / 1000) * speed;
    if (state.clock >= end) { state.clock = Infinity; stop(); draw(); return; }
    draw();
    if (window.rpScene) window.rpScene.setHealth(health());
    state.raf = requestAnimationFrame(tick);
  };
  state.raf = requestAnimationFrame(tick);
}

function health() {
  const d = state.attack.sides.at(-1);
  const { ok, bad } = series(d);
  const t = Math.floor(state.clock);
  let o = 0, b = 0;
  for (let k = Math.max(0, t - 2); k <= t && k < ok.length; k++) { o += ok[k]; b += bad[k]; }
  return o + b ? o / (o + b) : 1;
}

function stop() {
  cancelAnimationFrame(state.raf);
  state.playing = false;
  $("#rt-play").textContent = "▶ Launch the attack";
  if (window.rpScene) window.rpScene.setHealth(1);
}

$("#rt-play").addEventListener("click", () => {
  if (state.playing) { stop(); state.clock = Infinity; draw(); } else play();
});

init().catch(() => { $("#brief").innerHTML = "<p>Attack data is missing.</p>"; });
