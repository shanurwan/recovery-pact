"""Guardian turns and the deterministic grounding check.

Every LLM turn is validated before it counts:

- schema: the JSON must parse into Proposal / Review
- grounding: the candidate must exist, cited evidence ids must exist, probes must
  be on the menu, and a termination must cite the lock graph that observed it
- invariants: a Continuity acceptance of a termination is downgraded when the
  registry or calendar evidence it requires is missing, or when the registry
  marks the target never_interrupt / protected / unknown

An ungrounded turn is sent back once with the problems listed. A second failure
becomes an escalation; it never becomes an action.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import ValidationError

from app.agents.prompts import (
    CONTINUITY_GUARDIAN_SYSTEM,
    DB_GUARDIAN_SYSTEM,
    PROPOSAL_SCHEMA,
    REVIEW_SCHEMA,
    SOLO_SYSTEM,
    probes_block,
)
from app.config import get_settings
from app.evidence.collector import EvidenceLedger
from app.integrations.nemotron.client import get_inference_client
from app.schemas.enums import CandidateKind, ChallengeDecision
from app.schemas.pact import PROBES, Candidate, GroundingResult, Proposal, Review

logger = logging.getLogger(__name__)

DB_GUARDIAN = "database_guardian"
CONTINUITY_GUARDIAN = "continuity_guardian"
SOLO_AGENT = "solo_agent"


@dataclass
class TurnContext:
    incident_summary: str
    round: int
    max_rounds: int
    candidates: list[Candidate]
    ledger: EvidenceLedger
    memory_context: str
    transcript: list[str]
    call_key_prefix: str

    def candidate(self, cid: str) -> Candidate | None:
        return next((c for c in self.candidates if c.candidate_id == cid), None)

    def render(self) -> str:
        cands = "\n".join(
            f"- {c.candidate_id} [{c.kind.value}]: {c.description}"
            + (f" (observed in {c.evidence_id})" if c.evidence_id else "")
            for c in self.candidates
        )
        evidence = "\n".join(e.brief() for e in self.ledger.all()) or "(none)"
        transcript = "\n".join(self.transcript) or "(this is the opening turn)"
        return (
            f"INCIDENT: {self.incident_summary}\n"
            f"ROUND: {self.round} of {self.max_rounds}\n\n"
            f"CANDIDATES:\n{cands}\n\n"
            f"EVIDENCE:\n{evidence}\n\n"
            f"PROBES you may request:\n{probes_block()}\n\n"
            f"MEMORY (weak evidence):\n{self.memory_context or '(no relevant memories)'}\n\n"
            f"NEGOTIATION SO FAR:\n{transcript}\n"
        )


@dataclass
class TurnRecord:
    actor: str
    parsed: Any
    grounding: GroundingResult
    metrics: list[dict[str, Any]] = field(default_factory=list)
    attempts: int = 1
    failed: bool = False


_EVIDENCE_ID = re.compile(r"(?<![\w-])(?:DB|TEL|BIZ|MEM)-\d+(?![\w])")


def _clean_ids(raw: dict[str, Any], *keys: str) -> dict[str, Any]:
    """Normalize formatting, never meaning.

    Models echo ids the way they were displayed ("[DB-1]", "EVIDENCE: DB-1").
    Evidence ids are extracted by pattern; probe names are trimmed. Whether the
    ids exist is still decided by the grounding check.
    """
    raw = dict(raw)
    for k in keys:
        v = raw.get(k)
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, list):
            continue
        out: list[str] = []
        for x in v:
            x = str(x)
            if k.endswith("evidence") and not k.startswith("required"):
                found = _EVIDENCE_ID.findall(x)
                out.extend(found or [x.strip()])
            else:
                out.append(x.strip().strip("[]()<>'\" ").strip())
        raw[k] = list(dict.fromkeys(o for o in out if o))
    if isinstance(raw.get("candidate_id"), str):
        raw["candidate_id"] = raw["candidate_id"].strip().strip("[]'\" ")
    return raw


def _resolve_candidate(cid: str, ctx: "TurnContext") -> str:
    """Map an unambiguous shorthand ("terminate") to the one candidate it can mean."""
    if ctx.candidate(cid):
        return cid
    low = cid.lower()
    matches = [
        c.candidate_id
        for c in ctx.candidates
        if c.candidate_id.lower().startswith(low) or c.kind.value.lower() == low
    ]
    return matches[0] if len(matches) == 1 else cid


ROLE_OF = {"database_guardian": "database_guardian", "continuity_guardian": "continuity_guardian", "solo_agent": "solo_agent"}


def scaffold_on() -> bool:
    return get_settings().reasoning_scaffold


def _call(system: str, user: str, call_key: str, actor: str) -> tuple[dict[str, Any], dict[str, Any]]:
    model = get_settings().model_for(ROLE_OF.get(actor, actor))
    return get_inference_client().complete_json(system=system, user=user, call_key=call_key, model=model)


def _run_turn(
    actor: str,
    system: str,
    user: str,
    call_key: str,
    parse: Callable[[dict[str, Any]], Any],
    ground: Callable[[Any], GroundingResult],
) -> TurnRecord:
    metrics: list[dict[str, Any]] = []
    feedback = ""
    for attempt in (1, 2):
        try:
            raw, m = _call(system, user + feedback, f"{call_key}-a{attempt}", actor)
        except Exception as exc:  # noqa: BLE001 — inference down: fail closed, escalate
            logger.warning("%s inference unavailable: %s", actor, exc)
            return TurnRecord(
                actor,
                None,
                GroundingResult(ok=False, problems=[f"inference unavailable: {str(exc)[:200]}"]),
                metrics,
                attempt,
                failed=True,
            )
        metrics.append(m)
        try:
            parsed = parse(raw)
        except (ValidationError, ValueError, KeyError, TypeError) as exc:
            problems = [f"invalid JSON for the required shape: {str(exc)[:300]}"]
            feedback = _retry_note(problems)
            continue
        g = ground(parsed) if scaffold_on() else _exists_only(parsed)
        if g.ok or not scaffold_on():
            return TurnRecord(actor, parsed, g, metrics, attempt, failed=not g.ok)
        feedback = _retry_note(g.problems)
    return TurnRecord(
        actor,
        None,
        GroundingResult(ok=False, problems=["two ungrounded attempts"]),
        metrics,
        2,
        failed=True,
    )


def _exists_only(parsed: Any) -> GroundingResult:
    return GroundingResult(ok=True)


def _retry_note(problems: list[str]) -> str:
    return (
        "\n\nYOUR PREVIOUS ANSWER WAS REJECTED BY THE GROUNDING CHECK:\n- "
        + "\n- ".join(problems)
        + "\nFix these problems and answer again with ONLY the JSON object."
    )


# ------------------------------------------------------------------ proposals


def ground_proposal(p: Proposal, ctx: TurnContext) -> GroundingResult:
    problems: list[str] = []
    cand = ctx.candidate(p.candidate_id)
    if not cand:
        problems.append(
            f"candidate_id '{p.candidate_id}' is not in CANDIDATES "
            f"({', '.join(c.candidate_id for c in ctx.candidates)})"
        )
    missing = [e for e in p.cited_evidence if not ctx.ledger.has(e)]
    if missing:
        problems.append(
            f"cited evidence ids do not exist: {missing}. Valid ids: "
            + ", ".join(e.evidence_id for e in ctx.ledger.all())
        )
    if not p.cited_evidence:
        problems.append("cite at least one evidence id")
    bad_probes = [x for x in p.requested_probes if x not in PROBES]
    if bad_probes:
        problems.append(f"unknown probes: {bad_probes}")
    if cand and cand.kind == CandidateKind.TERMINATE and cand.evidence_id not in p.cited_evidence:
        problems.append(
            f"a termination must cite the lock graph that observed its target ({cand.evidence_id})"
        )
    return GroundingResult(ok=not problems, problems=problems)


def database_guardian_turn(ctx: TurnContext, revising: bool | str) -> TurnRecord:
    if revising == "investigated":
        task = (
            "YOUR TASK: The probes you requested have returned (see EVIDENCE). Confirm your proposal "
            "or change it in light of the new evidence. List what you changed in `changes`."
        )
    elif revising:
        task = (
            "YOUR TASK: Revise your proposal to answer the Continuity Guardian's review. "
            "You may change the candidate. List what you changed in `changes`."
        )
    else:
        task = "YOUR TASK: Propose one candidate action to resolve the incident."
    checklist = f"\n{evidence_checklist(ctx)}\n" if scaffold_on() else ""
    user = ctx.render() + f"{checklist}\n{task}\nRespond with ONLY JSON matching:\n{PROPOSAL_SCHEMA}"

    def parse(raw: dict[str, Any]) -> Proposal:
        raw = _clean_ids(raw, "cited_evidence", "requested_probes")
        raw["candidate_id"] = _resolve_candidate(str(raw.get("candidate_id", "")), ctx)
        raw["round"] = ctx.round
        return Proposal.model_validate(raw)

    return _run_turn(
        DB_GUARDIAN,
        DB_GUARDIAN_SYSTEM,
        user,
        f"{ctx.call_key_prefix}/db-r{ctx.round}" + ("i" if revising == "investigated" else ""),
        parse,
        lambda p: ground_proposal(p, ctx),
    )


def solo_agent_turn(ctx: TurnContext) -> TurnRecord:
    user = (
        ctx.render()
        + "\nYOUR TASK: Choose one candidate action to resolve the incident now."
        + f"\nRespond with ONLY JSON matching:\n{PROPOSAL_SCHEMA}"
    )

    def parse(raw: dict[str, Any]) -> Proposal:
        raw = _clean_ids(raw, "cited_evidence", "requested_probes")
        raw["candidate_id"] = _resolve_candidate(str(raw.get("candidate_id", "")), ctx)
        raw["round"] = ctx.round
        return Proposal.model_validate(raw)

    return _run_turn(
        SOLO_AGENT,
        SOLO_SYSTEM,
        user,
        f"{ctx.call_key_prefix}/solo-r{ctx.round}",
        parse,
        lambda p: ground_proposal(p, ctx),
    )


# -------------------------------------------------------------------- reviews


CHECKLIST_PROBES = (
    "biz.workload_registry",
    "biz.change_calendar",
    "db.protected_settlements",
    "biz.tradeoff",
)


def evidence_checklist(ctx: TurnContext) -> str:
    """Which decision-relevant probes are already in evidence: computed, not recalled."""
    lines = []
    for probe in CHECKLIST_PROBES:
        found = ctx.ledger.by_probe(probe)
        state = f"PRESENT ({', '.join(e.evidence_id for e in found)})" if found else "MISSING"
        lines.append(f"- {probe}: {state}")
    for c in ctx.candidates:
        if c.kind != CandidateKind.TERMINATE:
            continue
        app = c.target.get("application_name")
        window = _active_owner_window(ctx, app)
        if window:
            lines.append(f"- I3 APPLIES to {c.candidate_id}: active consult_owner window {window}")
        bad = _ineffective_memory(ctx, app)
        if bad:
            lines.append(f"- MEMORY VETO on {c.candidate_id}: terminating it was verified ineffective before {bad}")
    return "EVIDENCE CHECKLIST (computed by the orchestrator, authoritative):\n" + "\n".join(lines)


def ground_review(r: Review, ctx: TurnContext) -> GroundingResult:
    problems: list[str] = []
    redundant = [p for p in r.required_evidence if p != "db.lock_graph" and ctx.ledger.latest(p)]
    if (
        r.decision == ChallengeDecision.REQUEST_REVISION
        and r.required_evidence
        and len(redundant) == len(r.required_evidence)
    ):
        problems.append(
            f"required_evidence {redundant} is already PRESENT in EVIDENCE (see the checklist). "
            "Decide on the evidence you have (ACCEPT, CONDITIONAL_ACCEPT, REJECT or ESCALATE), "
            "or request only probes that are MISSING"
        )
    missing = [e for e in r.cited_evidence if not ctx.ledger.has(e)]
    if missing:
        problems.append(
            f"cited evidence ids do not exist: {missing}. Valid ids: "
            + ", ".join(e.evidence_id for e in ctx.ledger.all())
        )
    bad = [x for x in r.required_evidence if x not in PROBES]
    if bad:
        problems.append(f"unknown probes in required_evidence: {bad}")
    if r.decision == ChallengeDecision.REQUEST_REVISION and not (r.required_evidence or r.objection):
        problems.append("REQUEST_REVISION needs an objection or required_evidence")
    return GroundingResult(ok=not problems, problems=problems)


def enforce_business_invariants(
    review: Review, proposal: Proposal, ctx: TurnContext
) -> Review:
    """Hard business invariants, applied in code after the model decides.

    The model is told these rules; this makes sure an acceptance that breaks
    them can never leave the negotiation.
    """
    cand = ctx.candidate(proposal.candidate_id)
    accepting = review.decision in (ChallengeDecision.ACCEPT, ChallengeDecision.CONDITIONAL_ACCEPT)
    if accepting and cand and cand.kind == CandidateKind.WAIT:
        return _enforce_wait_tolerance(review, ctx)
    if not (accepting and cand and cand.kind == CandidateKind.TERMINATE):
        return review
    app = cand.target.get("application_name")
    registry = [
        rec
        for ev in ctx.ledger.by_probe("biz.workload_registry")
        for rec in ev.facts.get("records", [])
        if rec.get("application_name") == app
    ]
    # An unreachable source is unknown, not empty: it never satisfies I2 or I4.
    registry_probed = any(
        app in (ev.summary or "")
        for ev in ctx.ledger.by_probe("biz.workload_registry")
        if ev.source != "business_unavailable"
    )
    calendar_probed = any(
        app in (ev.summary or "") or app in str(ev.facts)
        for ev in ctx.ledger.by_probe("biz.change_calendar")
        if ev.source != "business_unavailable"
    )
    override: tuple[ChallengeDecision, str, list[str], list[str]] | None = None
    owner_window = _active_owner_window(ctx, app)
    ineffective = _ineffective_memory(ctx, app)
    if owner_window:
        override = (
            ChallengeDecision.ESCALATE,
            f"I3: active change window {owner_window} requires the owner to decide",
            ["I3"],
            [],
        )
    elif ineffective:
        override = (
            ChallengeDecision.ESCALATE,
            f"M1: memory {ineffective} records that terminating {app} was verified ineffective; "
            "memory may veto a repeat, never permit one",
            ["M1"],
            [],
        )
    elif registry:
        rec = registry[0]
        if rec.get("interrupt_policy") == "never_interrupt" or rec.get("workload_class") == "PROTECTED_SETTLEMENT":
            override = (ChallengeDecision.REJECT, "I1: registry marks the target never_interrupt", ["I1"], [])
        elif "dq_valid" in rec and rec["dq_valid"] is not True:
            rules = ", ".join(rec.get("dq_failed_rules") or []) or "rules could not be run"
            override = (ChallengeDecision.REJECT, f"I9: the registry row for the target fails Zetaris data quality "
                        f"({rules}); a record that contradicts itself can't vouch for a kill", ["I9"], [])
    elif registry_probed:
        override = (ChallengeDecision.REJECT, "I4: target is unknown to the workload registry", ["I4"], [])
    if override is None:
        need = []
        if not registry_probed:
            need.append("biz.workload_registry")
        if not calendar_probed:
            need.append("biz.change_calendar")
        if need:
            override = (
                ChallengeDecision.REQUEST_REVISION,
                "I2: acceptance requires registry and calendar evidence for the target",
                ["I2"],
                need,
            )
    if override is None:
        return review
    decision, why, invariants, need = override
    return review.model_copy(
        update={
            "decision": decision,
            "objection": f"[invariant override] {why}. Model said {review.decision.value}: {review.objection}".strip(),
            "violated_invariants": sorted(set(review.violated_invariants) | set(invariants)),
            "required_evidence": sorted(set(review.required_evidence) | set(need)),
        }
    )


def _active_owner_window(ctx: TurnContext, app: str | None) -> str | None:
    for ev in ctx.ledger.by_probe("biz.change_calendar"):
        for rec in ev.facts.get("records", []):
            if rec.get("application_name") == app and rec.get("policy") == "consult_owner":
                return f"{rec.get('change_id')} ({ev.evidence_id})"
    return None


def _ineffective_memory(ctx: TurnContext, app: str | None) -> str | None:
    """A recalled, non-superseded memory that this exact termination failed verification."""
    for ev in ctx.ledger.by_probe("mem.recall"):
        for m in ev.facts.get("recalled", []):
            tags = m.get("tags") or []
            if f"ck:terminate:{app}" in tags and "verdict:ineffective" in tags and not m.get("superseded"):
                return f"{m.get('id')} ({ev.evidence_id})"
    return None


def _enforce_wait_tolerance(review: Review, ctx: TurnContext) -> Review:
    """I7: waiting must fit inside the degradation the business says it tolerates."""
    trade = ctx.ledger.latest("biz.tradeoff")
    if not trade:
        return review.model_copy(
            update={
                "decision": ChallengeDecision.REQUEST_REVISION,
                "objection": "[invariant override] I7: cannot accept waiting without knowing how long "
                f"the blocker will run. Model said {review.decision.value}: {review.objection}",
                "violated_invariants": sorted(set(review.violated_invariants) | {"I7"}),
                "required_evidence": sorted(set(review.required_evidence) | {"biz.workload_registry"}),
            }
        )
    rows = trade.facts.get("rows", [])
    if rows and all(r.get("wait_within_tolerance") for r in rows):
        return review
    worst = max(rows, key=lambda r: r.get("expected_remaining_s") or 0) if rows else {}
    return review.model_copy(
        update={
            "decision": ChallengeDecision.REJECT,
            "objection": (
                f"[invariant override] I7: waiting ~{worst.get('expected_remaining_s')}s exceeds the "
                f"{worst.get('max_degradation_s')}s of degraded checkout the business tolerates "
                f"(~${worst.get('wait_cost_usd')} at risk, {trade.evidence_id}). "
                f"Model said {review.decision.value}: {review.objection}"
            ),
            "violated_invariants": sorted(set(review.violated_invariants) | {"I7"}),
        }
    )


def continuity_guardian_turn(ctx: TurnContext, proposal: Proposal) -> TurnRecord:
    user = (
        ctx.render()
        + f"\nPROPOSAL UNDER REVIEW (round {ctx.round}): candidate {proposal.candidate_id}. "
        f"Rationale: {proposal.rationale} Cited: {proposal.cited_evidence}. "
        f"Expected effect: {proposal.expected_effect}\n\n"
        + (f"{evidence_checklist(ctx)}\n\n" if scaffold_on() else "")
        + "YOUR TASK: Review this proposal against the business invariants."
        f"\nRespond with ONLY JSON matching:\n{REVIEW_SCHEMA}"
    )

    def parse(raw: dict[str, Any]) -> Review:
        raw = _clean_ids(raw, "cited_evidence", "required_evidence")
        raw["round"] = ctx.round
        raw["review_id"] = f"rev-{uuid.uuid4().hex[:8]}"
        if isinstance(raw.get("decision"), str):
            raw["decision"] = raw["decision"].strip().upper()
        return Review.model_validate(raw)

    rec = _run_turn(
        CONTINUITY_GUARDIAN,
        CONTINUITY_GUARDIAN_SYSTEM,
        user,
        f"{ctx.call_key_prefix}/cg-r{ctx.round}",
        parse,
        lambda r: ground_review(r, ctx),
    )
    if rec.parsed is not None and scaffold_on():
        enforced = enforce_business_invariants(rec.parsed, proposal, ctx)
        if enforced.decision != rec.parsed.decision:
            rec.grounding.overridden = enforced.objection
        rec.parsed = enforced
    return rec
