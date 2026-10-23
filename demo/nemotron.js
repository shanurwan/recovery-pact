// "Built on Nemotron" page. Every sentence that states a result is computed from data/nemotron.json.
"use strict";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const SHORT = {
  ultra: "Ultra 550B-A55B", super: "Super 120B-A12B", lightning: "Lightning 30B-A3B",
  lightning_no_scaffold: "Lightning, scaffold off", mixed: "Mixed team",
};
const SCEN = {
  A: "Routine fix", B: "Card settlement", C: "Moving target", D: "Forged order",
  E: "Job comes back", F: "Mystery session", G: "Quarter-end close", H: "Poisoned note",
};

const bad = (c) => c.unsafe_actions + c.business_harm + c.false_recovery_claims;

function bars(title, rows, note) {
  const max = Math.max(1, ...rows.map((r) => r.max ?? r.value));
  return `<div class="chart-card glass"><h3>${esc(title)}</h3><div class="bars">
    ${rows.map((r) => `<div class="bar"><span class="lbl" title="${esc(r.label)}">${esc(r.label)}</span>
      <span class="track"><span class="fill ${r.tone || ""}" style="width:${Math.max(r.value ? 2 : 0, (r.value / (r.max ?? max)) * 100)}%"></span></span>
      <span class="val">${esc(r.text ?? r.value)}</span></div>`).join("")}
  </div>${note ? `<p class="note">${esc(note)}</p>` : ""}</div>`;
}

function correctBars(cs) {
  return bars("Right calls", cs.map((c) => ({ label: SHORT[c.key], value: c.correct, max: c.runs, text: `${c.correct}/${c.runs}`, tone: c.correct === c.runs ? "good" : "" })));
}
function harmBars(cs) {
  return bars("Unsafe actions + business harm + false “fixed” claims", cs.map((c) => ({ label: SHORT[c.key], value: bad(c), max: Math.max(3, ...cs.map(bad)), text: bad(c), tone: bad(c) ? "bad" : "good" })), "Lower is better. Zero means nothing protected was touched and no recovery was misreported.");
}

function perScenarioTable(cs) {
  const keys = Object.keys(cs[0].per_scenario);
  return `<table><thead><tr><th>Incident</th>${cs.map((c) => `<th>${esc(SHORT[c.key])}</th>`).join("")}</tr></thead><tbody>
    ${keys.map((k) => `<tr><td>${esc(SCEN[k[0]] || k)}</td>${cs.map((c) => {
      const v = c.per_scenario[k] || "–"; const [a, b] = v.split("/");
      return `<td class="num ${a === b ? "ok" : a === "0" ? "no" : ""}">${esc(v)}</td>`;
    }).join("")}</tr>`).join("")}</tbody></table>`;
}

async function init() {
  let data;
  try {
    data = await (await fetch("data/nemotron.json")).json();
  } catch (e) {
    $("#s-scaling").textContent = "Benchmark data is missing. Build it with python -m app.evals.build_nemotron.";
    return;
  }
  const by = Object.fromEntries(data.configs.map((c) => [c.key, c]));
  const family = ["ultra", "super", "lightning"].map((k) => by[k]).filter(Boolean);
  const scaffoldOn = data.configs.filter((c) => c.reasoning_scaffold);
  const runsTotal = data.configs.reduce((n, c) => n + c.runs, 0);
  const guardUsed = (data.guard?.configs || []).find((g) => g.config.startsWith("RecoveryPact runtime guard"));

  // Headline
  const onBad = scaffoldOn.reduce((n, c) => n + bad(c), 0);
  const stat = (big, what, sub) => `<div class="hstat glass"><span class="big">${big}</span><span class="what">${what}</span><span class="them">${sub}</span></div>`;
  $("#nv-headline").innerHTML = [
    stat(family.length + 2, "Nemotron models at work", "reasoning, safety and embedding models"),
    stat(runsTotal, "benchmarked incident runs", `${data.configs.length} configurations × 8 incidents × 3 repeats`),
    stat(onBad, "unsafe, harmful or false calls", `across all ${scaffoldOn.length} scaffolded configurations`),
    guardUsed ? stat(guardUsed.injections_caught, "hidden injections caught", `${guardUsed.false_positives} false positives`) : "",
  ].join("");

  // Roles
  const roles = [
    ["Database AI", by.ultra?.models_by_role?.database_guardian, "Proposes the recovery, requests evidence, revises under challenge."],
    ["Business AI", by.ultra?.models_by_role?.continuity_guardian, "Reads company records through Zetaris, weighs costs, accepts, rejects or escalates. The judgement-heavy role."],
    ["Auditor AI", by.ultra?.models_by_role?.auditor, "Writes the incident report and the lesson memory keeps."],
    ["Injection guard", "llama-3.1-nemotron-safety-guard-8b-v3 + nemotron-3.5-lightning-30b-a3b", "Screens every untrusted string before an agent reads it. Two layers in parallel; either one quarantines."],
    ["Memory embeddings", "nemotron-3-embed-1b", "Meterless H-MEM recall of past incidents and what the counterpart required."],
  ];
  $("#roles").innerHTML = roles.map(([n, m, d]) => `<div class="role glass"><span class="r-name">${esc(n)}</span><span class="r-model">${esc((m || "").replace("nvidia/", ""))}</span><p>${esc(d)}</p></div>`).join("");

  // Finding 1: family
  if (family.length) {
    const famBad = family.reduce((n, c) => n + bad(c), 0);
    $("#t-scaling").textContent = famBad === 0 ? "Zero unsafe actions on every Nemotron size" : "What changes across Nemotron sizes";
    const best = [...family].sort((a, b) => b.correct - a.correct || a.median_duration_s - b.median_duration_s)[0];
    $("#s-scaling").textContent = (famBad === 0
      ? "The safety properties hold from 3B active parameters to 55B: no size stopped a protected workload, did what the business ruled out, or misreported a recovery. "
      : `Across sizes there were ${famBad} unsafe, harmful or false calls in total. `)
      + `Right calls: ${family.map((c) => `${SHORT[c.key]} ${c.correct}/${c.runs}`).join(", ")}. `
      + `${SHORT[best.key]} reached the right call most often with a median of ${best.median_duration_s} s per incident.`;
    $("#c-scaling").innerHTML = correctBars(family) + harmBars(family)
      + bars("Median time per incident (s)", family.map((c) => ({ label: SHORT[c.key], value: c.median_duration_s, tone: "neutral" })), "Includes the verification window and, in some incidents, deliberate waiting.")
      + bars("Tokens per incident", family.map((c) => ({ label: SHORT[c.key], value: c.mean_tokens_per_incident || 0, text: (c.mean_tokens_per_incident || 0).toLocaleString(), tone: "neutral" })));
  }

  // Finding 2: scaffold ablation
  const on = by.lightning, off = by.lightning_no_scaffold;
  if (on && off) {
    const worse = bad(off) > bad(on) || off.correct < on.correct;
    $("#t-ablation").textContent = worse ? "The scaffold is what makes a 3B-active Nemotron dependable" : "Scaffold on vs off";
    $("#s-ablation").textContent = `Same model (Lightning, 3B active), same incidents. With the scaffold: ${on.correct}/${on.runs} right calls and ${bad(on)} unsafe, harmful or false calls. `
      + `Without it (no grounding retries, evidence checklist, trade-off calculator, code-enforced invariants or injection guard): ${off.correct}/${off.runs} right and ${bad(off)} unsafe, harmful or false. `
      + "The deterministic safety authority stayed on in both, so this isolates the reasoning scaffold.";
    $("#c-ablation").innerHTML = correctBars([on, off]) + harmBars([on, off]);
    $("#tbl-ablation").innerHTML = perScenarioTable([on, off]);
  }

  // Finding 3: mixed team
  const mixed = by.mixed, ultra = by.ultra;
  if (mixed && ultra) {
    const lat = (c, role) => c.median_turn_latency_ms?.[role];
    $("#s-mixed").textContent = `Ultra only for the Business AI's judgement, Lightning for the Database AI and the Auditor: ${mixed.correct}/${mixed.runs} right calls and ${bad(mixed)} unsafe, harmful or false, `
      + `against ${ultra.correct}/${ultra.runs} and ${bad(ultra)} with every agent on Ultra. Median per incident: ${mixed.median_duration_s} s vs ${ultra.median_duration_s} s.`
      + (lat(mixed, "database_guardian") && lat(ultra, "database_guardian") ? ` Database AI turns took a median ${lat(mixed, "database_guardian")} ms on Lightning vs ${lat(ultra, "database_guardian")} ms on Ultra.` : "");
    const cs = [ultra, mixed, by.lightning].filter(Boolean);
    $("#c-mixed").innerHTML = correctBars(cs) + harmBars(cs)
      + bars("Median time per incident (s)", cs.map((c) => ({ label: SHORT[c.key], value: c.median_duration_s, tone: "neutral" })));
  }

  // Finding 4: guard + scenario H
  if (data.guard) {
    const g = data.guard.configs;
    const plainBest = Math.max(...g.filter((x) => x.config.includes("out of the box")).map((x) => x.recall));
    $("#s-guard").textContent = `Anyone who can run a query or edit a CSV can plant words addressed to an AI. On ${data.guard.cases} labelled strings, NVIDIA's safety models out of the box caught up to ${Math.round(plainBest * 100)}% of the hidden instructions (they target harmful content, not injection). `
      + (guardUsed ? `RecoveryPact's runtime guard, Nemotron Safety Guard plus a small reasoning Nemotron asked one narrow question, caught ${guardUsed.injections_caught} with ${guardUsed.false_positives} false positives at a median ${Math.round(guardUsed.median_latency_ms)} ms.` : "");
    $("#tbl-guard").innerHTML = `<table><thead><tr><th>Configuration</th><th>Injections caught</th><th>False positives</th><th>Median latency</th></tr></thead><tbody>
      ${g.map((x) => `<tr><td>${esc(x.config)}</td><td class="num">${esc(x.injections_caught)}</td><td class="num">${esc(x.false_positives)}</td><td class="num">${Math.round(x.median_latency_ms)} ms</td></tr>`).join("")}</tbody></table>`;
  }
  const inj = data.configs.filter((c) => c.injection);
  if (inj.length) {
    $("#tbl-inject").innerHTML = `<table><thead><tr><th>The poisoned-note incident</th><th>Right call</th><th>Injection quarantined</th><th>Obeyed the note (harm)</th></tr></thead><tbody>
      ${inj.map((c) => `<tr><td>${esc(SHORT[c.key])}</td><td class="num">${c.injection.correct}/${c.injection.runs}</td><td class="num">${c.injection.flagged}/${c.injection.runs}</td><td class="num ${c.injection.harm ? "no" : "ok"}">${c.injection.harm}</td></tr>`).join("")}</tbody></table>`;
  }

  const zet = data.configs[0]?.zetaris_mode === "zetaris" ? "live Zetaris federation" : "the labelled local fallback";
  $("#method").textContent = `Each configuration ran the pact on 8 incidents with real PostgreSQL locks and real checkout traffic, ${data.configs[0]?.repeats || 3} independent repeats, business context through ${zet}. `
    + "Correctness is judged against fixed ground truth per incident, and every number above was recomputed from raw run traces by the repository's validator.";
}

init();
