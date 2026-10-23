"""Meterless H-MEM: durable, ranked, self-correcting memory for the guardians.

A port of the Meterless H-MEM contracts (github.com/Meterless/Meterless):

- memory model with layers short_term / working / long_term (weights 0.6/0.8/1.0)
- ranking, verbatim (keyword/tag/entity are Jaccard, recency decays from last access):
      raw = 0.35*semantic + 0.20*keyword + 0.10*tag + 0.10*domain
          + 0.15*entity + 0.05*layer + 0.05*recency - 0.20*superseded
      score = clamp01(raw) * confidence
- feedback deltas: helpful +0.05 and accessCount+1, not_helpful -0.03, wrong -0.20 + review tag
- conflicts on the same claim key: the newer verified claim supersedes the
  older one, which is penalised in ranking but never deleted; plus the spec's
  general scan (opposing phrases, conflicting numbers) behind the 0.70 auto-resolve gate
- append-only trust ledger (SQLite triggers) with previous/new state per entry
- sleep (preview-first, guardrails, backup and restore) and dreaming (proposals
  that only become memory on approval)
- reinjection block ``[MEMORY CONTEXT] ... [/MEMORY CONTEXT]``

Checked against Meterless's own conformance vectors
(engines/hmem/conformance/vectors/vectors.json, vendored in tests/meterless/):
see tests/test_hmem_conformance.py.

Storage is SQLite and the embedder is NVIDIA Nemotron embeddings when a key is
present, else the spec's FNV-1a 64-dim mock. Vectors from different embedders
never compare (cosine 0).

Memory is weak evidence. It changes which evidence the guardians gather and
what they expect; it never authorises anything.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

TOP_N = 5
RECENCY_DAYS = 14.0
ENTITY_CAP = 10
RELATED_CAP = 5
CONFLICT_GATE = 0.70
PROMOTE_AFTER_HELPFUL = 2
FEEDBACK_DELTAS = {"helpful": 0.05, "not_helpful": -0.03, "wrong": -0.20}
LAYER_WEIGHT = {"long_term": 1.0, "working": 0.8, "short_term": 0.6}
WEIGHTS = {
    "semantic": 0.35,
    "keyword": 0.20,
    "tag": 0.10,
    "domain": 0.10,
    "entity": 0.15,
    "layer": 0.05,
    "recency": 0.05,
    "superseded": -0.20,
}
STOPWORDS = set(
    "a an the and or of to in on for by with is was were be been it its this that "
    "as at from into than then so not no".split()
)


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


# ------------------------------------------------------------------ embedders


class HashEmbedder:
    """The spec's mock embedder: FNV-1a over tokens into 64 dims."""

    name = "hash-fnv1a-64"

    def embed(self, text: str, kind: str = "passage") -> list[float]:
        vec = [0.0] * 64
        for tok in tokens(text):
            h = 0xCBF29CE484222325
            for b in tok.encode("utf-8"):
                h ^= b
                h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
            vec[h % 64] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class NvidiaEmbedder:
    """Nemotron embeddings (asymmetric query/passage) via the NIM API."""

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.name = f"nvidia:{model}"

    def embed(self, text: str, kind: str = "passage") -> list[float]:
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": [text[:4000]], "input_type": kind},
            )
            resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]


class MeterlessEmbedder:
    """Embeddings through Meterless Runtime (OpenAI-compatible /v1/embeddings)."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.name = f"meterless:{model}"

    def embed(self, text: str, kind: str = "passage") -> list[float]:
        from app.integrations.meterless import runtime

        s = get_settings()
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{runtime.normalize_base_url(s.meterless_base_url)}/embeddings",
                headers=runtime.headers(s.meterless_runtime_token),
                json={"model": self.model, "input": [text[:4000]], "input_type": kind},
            )
            resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]


class FallbackEmbedder:
    def __init__(self, primary: Any, fallback: HashEmbedder) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = primary.name

    def embed(self, text: str, kind: str = "passage") -> tuple[list[float], str]:
        try:
            return self.primary.embed(text, kind), self.primary.name
        except Exception as exc:  # noqa: BLE001
            logger.warning("embedder %s failed, using hash: %s", self.primary.name, exc)
            return self.fallback.embed(text, kind), self.fallback.name


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9_]+", text.lower()) if t not in STOPWORDS and len(t) > 1]


def jaccard(a: Any, b: Any) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    return inter / (len(sa) + len(sb) - inter)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def extract_entities(text: str) -> list[str]:
    """Workload identifiers: application names and job names (snake_case ids)."""
    found = re.findall(r"\b[a-z]+(?:_[a-z0-9]+)+\b", text)
    return list(dict.fromkeys(found))[:ENTITY_CAP]


def classify_domain(text: str, tags: list[str]) -> str:
    t = text.lower() + " " + " ".join(tags)
    if "settlement" in t or "calendar" in t or "owner" in t or "business" in t:
        return "business.continuity"
    if "lock" in t or "blocker" in t or "terminate" in t:
        return "db.locks"
    return "general"


# --------------------------------------------------------------------- store

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY,
  namespace TEXT NOT NULL,
  content TEXT NOT NULL,
  type TEXT NOT NULL,
  layer TEXT NOT NULL,
  domain TEXT NOT NULL,
  tags TEXT NOT NULL,
  entities TEXT NOT NULL,
  related_to TEXT NOT NULL,
  embedding TEXT NOT NULL,
  embedder TEXT NOT NULL,
  confidence REAL NOT NULL,
  access_count INTEGER NOT NULL DEFAULT 0,
  helpful_count INTEGER NOT NULL DEFAULT 0,
  source TEXT NOT NULL,
  provenance TEXT NOT NULL,
  supersedes TEXT,
  superseded_by TEXT,
  created_at REAL NOT NULL,
  last_accessed REAL NOT NULL,
  derived_from TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS ledger (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  memory_id TEXT NOT NULL,
  action TEXT NOT NULL,
  actor TEXT NOT NULL,
  details TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS backups (
  id TEXT PRIMARY KEY,
  ts REAL NOT NULL,
  records TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS ledger_no_update BEFORE UPDATE ON ledger
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS ledger_no_delete BEFORE DELETE ON ledger
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
"""


@dataclass
class Recalled:
    memory: dict[str, Any]
    relevance: float
    terms: dict[str, float]


@dataclass
class QueryResult:
    memories: list[Recalled] = field(default_factory=list)
    context: str = ""
    considered: int = 0


class HMEM:
    def __init__(
        self,
        path: str | Path,
        embedder: FallbackEmbedder | HashEmbedder,
        threshold: float,
        clock: Any = time.time,
        actor: str = "recovery-pact",
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder
        self.threshold = threshold
        self.clock = clock  # seconds; injectable so the conformance vectors can age records
        self.actor = actor
        self._lock = threading.Lock()
        self._init_schema()
        self.sleep = SleepCycle(self)
        self.conflicts = ConflictDetection(self)
        self.dreaming = Dreaming(self)

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.executescript(SCHEMA)
            cols = {r["name"] for r in c.execute("PRAGMA table_info(memories)")}
            if "derived_from" not in cols:
                c.execute("ALTER TABLE memories ADD COLUMN derived_from TEXT NOT NULL DEFAULT '[]'")

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _embed(self, text: str, kind: str) -> tuple[list[float], str]:
        if isinstance(self.embedder, FallbackEmbedder):
            return self.embedder.embed(text, kind)
        return self.embedder.embed(text, kind), self.embedder.name

    def _ledger(
        self,
        c: sqlite3.Connection,
        memory_id: str,
        action: str,
        details: dict[str, Any],
        previous: dict[str, Any] | None = None,
        new: dict[str, Any] | None = None,
    ) -> None:
        if previous is not None or new is not None:
            details = details | {"previousState": previous, "newState": new}
        c.execute(
            "INSERT INTO ledger (ts, memory_id, action, actor, details) VALUES (?,?,?,?,?)",
            (self.clock(), memory_id, action, self.actor, json.dumps(details, default=str)),
        )

    # --------------------------------------------------------------- write

    def add(
        self,
        content: str,
        *,
        namespace: str = "recovery-pact",
        type: str = "factual",
        layer: str = "working",
        tags: list[str] | None = None,
        entities: list[str] | None = None,
        confidence: float = 0.7,
        source: str = "verification",
        provenance: dict[str, Any] | None = None,
        conflict_key: str | None = None,
        verdict: str | None = None,
        derived_from: list[str] | None = None,
    ) -> dict[str, Any]:
        if not source or not str(source).strip():
            raise ValueError("H-MEM: every memory needs a source")  # spec: rejected by construction
        tags = list(tags or [])
        if conflict_key:
            tags += [f"ck:{conflict_key}", f"verdict:{verdict}"]
        tags = list(dict.fromkeys(tags))
        ents = list(dict.fromkeys(extract_entities(content) + list(entities or [])))[:ENTITY_CAP]
        vec, emb_name = self._embed(content, "passage")
        now = self.clock()
        mid = "mem-" + hashlib.sha256(f"{namespace}|{content}|{now}|{time.perf_counter_ns()}".encode()).hexdigest()[:16]
        related: list[str] = []
        supersedes: str | None = None
        with self._lock, self._conn() as c:
            if conflict_key:
                priors = c.execute(
                    "SELECT * FROM memories WHERE namespace=? AND superseded_by IS NULL AND tags LIKE ?",
                    (namespace, f'%"ck:{conflict_key}"%'),
                ).fetchall()
                for p in priors:
                    ptags = json.loads(p["tags"])
                    if f"verdict:{verdict}" in ptags:
                        related.append(p["id"])
                        continue
                    decision = 0.8  # newer + independently verified beats older claim
                    self._ledger(c, p["id"], "conflict_detected", {"with": mid, "key": conflict_key})
                    if decision >= CONFLICT_GATE:
                        c.execute("UPDATE memories SET superseded_by=? WHERE id=?", (mid, p["id"]))
                        supersedes = p["id"]
                        self._ledger(
                            c, p["id"], "conflict_resolved", {"winner": mid, "confidence": decision},
                            previous={"supersededBy": None}, new={"supersededBy": mid},
                        )
            c.execute(
                "INSERT INTO memories (id, namespace, content, type, layer, domain, tags, entities, related_to, "
                "embedding, embedder, confidence, source, provenance, supersedes, created_at, last_accessed, derived_from) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    mid,
                    namespace,
                    content,
                    type,
                    layer,
                    classify_domain(content, tags),
                    json.dumps(tags),
                    json.dumps(ents),
                    json.dumps(related[:RELATED_CAP]),
                    json.dumps(vec),
                    emb_name,
                    clamp01(confidence),
                    source,
                    json.dumps(provenance or {}, default=str),
                    supersedes,
                    now,
                    now,
                    json.dumps(list(derived_from or [])),
                ),
            )
            self._ledger(c, mid, "create", {"content": content, "tags": tags, "supersedes": supersedes},
                         new={"confidence": clamp01(confidence), "layer": layer})
        return self.get(mid) or {}

    def feedback(self, memory_id: str, verdict: str, reason: str = "") -> None:
        """Spec 9.2: helpful -> accessCount+1, conf+0.05; not_helpful -> -0.03; wrong -> -0.20 + review tag."""
        delta = FEEDBACK_DELTAS[verdict]
        with self._lock, self._conn() as c:
            row = c.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
            if not row:
                return
            conf = clamp01(row["confidence"] + delta)
            helpful = row["helpful_count"] + (1 if verdict == "helpful" else 0)
            access = row["access_count"] + (1 if verdict == "helpful" else 0)
            tags = json.loads(row["tags"])
            if verdict == "wrong" and "review" not in tags:
                tags.append("review")
            layer = row["layer"]
            c.execute(
                "UPDATE memories SET confidence=?, helpful_count=?, access_count=?, tags=? WHERE id=?",
                (conf, helpful, access, json.dumps(tags), memory_id),
            )
            self._ledger(
                c, memory_id, "feedback", {"kind": verdict, "delta": delta, "reason": reason},
                previous={"confidence": row["confidence"], "accessCount": row["access_count"]},
                new={"confidence": conf, "accessCount": access},
            )
            if layer == "working" and helpful >= PROMOTE_AFTER_HELPFUL:
                c.execute("UPDATE memories SET layer='long_term' WHERE id=?", (memory_id,))
                self._ledger(c, memory_id, "promote", {}, previous={"layer": "working"}, new={"layer": "long_term"})

    def set_superseded(self, memory_id: str, by: str | None) -> None:
        with self._lock, self._conn() as c:
            c.execute("UPDATE memories SET superseded_by=? WHERE id=?", (by, memory_id))
            self._ledger(c, memory_id, "update", {}, new={"supersededBy": by})

    def _update(self, memory_id: str, action: str, **fields: Any) -> None:
        sets = ", ".join(f"{k}=?" for k in fields)
        with self._lock, self._conn() as c:
            c.execute(f"UPDATE memories SET {sets} WHERE id=?", (*fields.values(), memory_id))
            self._ledger(c, memory_id, action, {}, new=fields)

    def _delete(self, memory_id: str, reason: str) -> None:
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM memories WHERE id=?", (memory_id,))
            self._ledger(c, memory_id, "delete", {"reason": reason})

    # ---------------------------------------------------------------- read

    def query(
        self,
        text: str,
        *,
        namespace: str = "recovery-pact",
        tags: list[str] | None = None,
        entities: list[str] | None = None,
        top_n: int = TOP_N,
        threshold: float | None = None,
    ) -> QueryResult:
        qvec, qemb = self._embed(text, "query")
        qtoks = [t for t, _ in sorted(_freq(tokens(text)).items(), key=lambda kv: (-kv[1], -len(kv[0])))][:8]
        qtags = {t.lower() for t in tags} if tags else set(qtoks)
        qents = set(entities or []) | set(extract_entities(text))
        qdomain = classify_domain(text, list(tags or []))
        now = self.clock()
        floor = self.threshold if threshold is None else threshold
        with self._conn() as c:
            rows = c.execute("SELECT * FROM memories WHERE namespace=?", (namespace,)).fetchall()
        scored: list[Recalled] = []
        for r in rows:
            m = _row(r)
            terms = {
                "semantic": clamp01(cosine(qvec, json.loads(r["embedding"]))) if r["embedder"] == qemb else 0.0,
                "keyword": jaccard(qtoks, tokens(m["content"])),
                "tag": jaccard(qtags, [t.lower() for t in m["tags"]]),
                "domain": 1.0 if m["domain"] == qdomain else 0.0,
                "entity": jaccard(qents, m["entities"]),
                "layer": LAYER_WEIGHT.get(m["layer"], 0.6),
                "recency": math.exp(-((now - m["last_accessed"]) / 86400.0) / RECENCY_DAYS),
                "superseded": 1.0 if m["superseded_by"] else 0.0,
            }
            raw = sum(WEIGHTS[k] * v for k, v in terms.items())
            score = clamp01(raw) * m["confidence"]
            if score >= floor:
                scored.append(Recalled(m, round(score, 4), {k: round(v, 3) for k, v in terms.items()}))
        scored.sort(key=lambda x: x.relevance, reverse=True)
        top = scored[:top_n]
        if top:
            with self._lock, self._conn() as c:
                for rc in top:
                    c.execute(
                        "UPDATE memories SET access_count=access_count+1, last_accessed=? WHERE id=?",
                        (now, rc.memory["id"]),
                    )
                    self._ledger(c, rc.memory["id"], "read", {"query": text[:200], "score": rc.relevance})
        return QueryResult(memories=top, context=reinjection(top), considered=len(rows))

    def get(self, memory_id: str) -> dict[str, Any] | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
        return _row(r) if r else None

    def _all(self, namespace: str | None = None) -> list[dict[str, Any]]:
        """Every record with its embedding, oldest first (used by sleep, conflicts and dreaming)."""
        sql, args = "SELECT * FROM memories", ()
        if namespace:
            sql, args = sql + " WHERE namespace=?", (namespace,)
        with self._conn() as c:
            rows = c.execute(sql + " ORDER BY created_at, rowid", args).fetchall()
        return [_row(r) | {"embedding": json.loads(r["embedding"])} for r in rows]

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [_row(r) for r in rows]

    def ledger(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM ledger ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) | {"details": json.loads(r["details"])} for r in rows]

    def history(self, memory_id: str) -> list[dict[str, Any]]:
        """Spec 9.1: reconstruct one memory's life from the append-only ledger."""
        with self._conn() as c:
            rows = c.execute("SELECT * FROM ledger WHERE memory_id=? ORDER BY seq", (memory_id,)).fetchall()
        out = []
        for r in rows:
            d = json.loads(r["details"])
            out.append({"memoryId": r["memory_id"], "action": r["action"], "actor": r["actor"], "timestamp": r["ts"],
                        "previousState": d.pop("previousState", None), "newState": d.pop("newState", None), "details": d})
        return out

    def clear(self) -> None:
        """Wipe memory for a cold-start run. Recreates the file, ledger included."""
        with self._lock:
            if self.path.exists():
                self.path.unlink()
            self._init_schema()


# ------------------------------------------------------------- sleep (spec 8)

CONSOLIDATION_DAYS = 7
ARCHIVE_MIN_DAYS = 30
ARCHIVE_MAX_ACCESS = 2
SYNTHESIS_COSINE = 0.82
HUB_THRESHOLD = 3


class SleepCycle:
    """Preview-first maintenance: consolidate, archive and synthesize, with guardrails and a backup."""

    def __init__(self, hmem: HMEM) -> None:
        self.h = hmem

    def preview(self) -> dict[str, Any]:
        now, day = self.h.clock(), 86400.0
        rows = self.h._all()
        referenced: set[str] = set()
        for m in rows:
            referenced.update(m["related_to"])
            referenced.update(m["derived_from"])
            if m["supersedes"]:
                referenced.add(m["supersedes"])
        to_consolidate = [m["id"] for m in rows
                          if m["layer"] == "short_term" and now - m["last_accessed"] >= CONSOLIDATION_DAYS * day]
        to_archive = [
            m["id"] for m in rows
            if now - m["created_at"] >= ARCHIVE_MIN_DAYS * day
            and m["access_count"] <= ARCHIVE_MAX_ACCESS
            and m["id"] not in referenced
            and not m["supersedes"]                       # superseding/current record
            and not m["derived_from"]                     # derived/synthesized memory
            and len(m["related_to"]) < HUB_THRESHOLD      # relationship hub
        ]
        to_synthesize: list[list[str]] = []
        used: set[str] = set()
        for i, a in enumerate(rows):
            if a["id"] in used:
                continue
            group = [a] + [b for b in rows[i + 1:] if b["id"] not in used
                           and cosine(a["embedding"], b["embedding"]) >= SYNTHESIS_COSINE]
            if len(group) >= 2:
                used.update(g["id"] for g in group)
                to_synthesize.append([g["id"] for g in group])
        return {"toConsolidate": to_consolidate, "toArchive": to_archive, "toSynthesize": to_synthesize}

    def execute(self, preview: dict[str, Any] | None = None) -> dict[str, Any]:
        plan = preview or self.preview()
        backup_id = f"backup-{int(self.h.clock() * 1000)}-{time.perf_counter_ns() % 100000}"
        snapshot = [dict(r) for r in self._raw_rows()]
        with self.h._lock, self.h._conn() as c:
            c.execute("INSERT INTO backups (id, ts, records) VALUES (?,?,?)",
                      (backup_id, self.h.clock(), json.dumps(snapshot, default=str)))
        log = [f"backup {backup_id} created"]
        for mid in plan["toConsolidate"]:
            if self.h.get(mid):
                self.h._update(mid, "sleep_consolidate", layer="long_term")
                log.append(f"consolidated {mid}")
        for mid in plan["toArchive"]:
            if self.h.get(mid):
                with self.h._lock, self.h._conn() as c:
                    self.h._ledger(c, mid, "sleep_archive", {})
                self.h._delete(mid, "sleep archive")
                log.append(f"archived {mid}")
        synthesized = 0
        for group in plan["toSynthesize"]:
            members = [m for m in (self.h.get(i) for i in group) if m]
            if len(members) < 2:
                continue
            merged = self.h.add(
                "Synthesis: " + " | ".join(m["content"] for m in members),
                namespace=members[0]["namespace"], layer="long_term",
                tags=list(dict.fromkeys(t for m in members for t in m["tags"])),
                confidence=max(m["confidence"] for m in members), source="sleep:synthesis",
                derived_from=[m["id"] for m in members],
            )
            with self.h._lock, self.h._conn() as c:
                self.h._ledger(c, merged["id"], "sleep_synthesize", {"sources": group})
            for m in members:
                self.h._delete(m["id"], "merged by sleep synthesis")
            synthesized += 1
            log.append(f"synthesized {merged['id']} from {', '.join(group)}")
        return {"backupId": backup_id, "consolidated": len(plan["toConsolidate"]),
                "archived": len(plan["toArchive"]), "synthesized": synthesized, "actionLog": log}

    def restore(self, backup_id: str) -> None:
        with self.h._lock, self.h._conn() as c:
            row = c.execute("SELECT records FROM backups WHERE id=?", (backup_id,)).fetchone()
            if not row:
                raise KeyError(f"H-MEM: unknown backup {backup_id}")
            c.execute("DELETE FROM memories")
            for rec in json.loads(row["records"]):
                cols = ", ".join(rec)
                c.execute(f"INSERT INTO memories ({cols}) VALUES ({', '.join('?' * len(rec))})", tuple(rec.values()))
            self.h._ledger(c, "*", "restore", {"backupId": backup_id})

    def _raw_rows(self) -> list[sqlite3.Row]:
        with self.h._conn() as c:
            return c.execute("SELECT * FROM memories").fetchall()


# --------------------------------------------------------- conflicts (spec 10)

OPPOSING_PAIRS = [
    (re.compile(r"\balways\b", re.I), re.compile(r"\bnever\b", re.I)),
    (re.compile(r"\benable[ds]?\b", re.I), re.compile(r"\bdisable[ds]?\b", re.I)),
    (re.compile(r"\bprefer[s]?\b", re.I), re.compile(r"\bavoid[s]?|dislike[s]?\b", re.I)),
    (re.compile(r"\bon\b", re.I), re.compile(r"\boff\b", re.I)),
    (re.compile(r"\byes\b", re.I), re.compile(r"\bno\b", re.I)),
]
_NUM = re.compile(r"\d+(?:\.\d+)?")


class ConflictDetection:
    def __init__(self, hmem: HMEM) -> None:
        self.h = hmem
        self._conflicts: list[dict[str, Any]] = []

    def scan(self) -> list[dict[str, Any]]:
        rows = self.h._all()
        found = []
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                conflict = self._check(a, b)
                if conflict:
                    found.append(conflict)
                    self._conflicts.append(conflict)
                    with self.h._lock, self.h._conn() as c:
                        self.h._ledger(c, a["id"], "conflict_detected",
                                       {"with": b["id"], "reason": conflict["reason"], "confidence": conflict["confidence"]})
        return found

    def _check(self, a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any] | None:
        if b["id"] in (a["supersedes"], a["superseded_by"]) or a["id"] in (b["supersedes"], b["superseded_by"]):
            return None  # an intended replacement, not a conflict
        sim = cosine(a["embedding"], b["embedding"])
        reason, conf = "", 0.0
        for p, q in OPPOSING_PAIRS:
            opposed = (p.search(a["content"]) and q.search(b["content"])) or (q.search(a["content"]) and p.search(b["content"]))
            if opposed and sim > 0.5:
                reason, conf = "opposing phrase pair on similar content", 0.5 + 0.3 * sim
        if not reason and sim > 0.8:
            na, nb = _NUM.findall(a["content"]), _NUM.findall(b["content"])
            if na and nb and na != nb:
                reason, conf = "high-similarity conflicting numeric values", 0.55 + 0.25 * sim
        if not reason:
            return None
        if set(a["entities"]) & set(b["entities"]):
            conf += 0.1
        if a["domain"] == b["domain"]:
            conf += 0.05
        if b["id"] in a["related_to"]:
            conf -= 0.1
        return {"id": f"conflict-{len(self._conflicts) + 1}", "memoryA": a["id"], "memoryB": b["id"],
                "reason": reason, "confidence": clamp01(conf), "resolved": False}

    def auto_resolve(self, conflict: dict[str, Any]) -> str:
        a, b = self.h.get(conflict["memoryA"]), self.h.get(conflict["memoryB"])
        now = max(1.0, self.h.clock())

        def score(m: dict[str, Any]) -> float:
            return (0.3 * (m["last_accessed"] / now) + 0.2 * min(1.0, m["access_count"] / 10) + 0.25 * m["confidence"]
                    + 0.1 * min(1.0, len(m["content"]) / 200)
                    + 0.15 * (1.0 if m["provenance"].get("origin") == "user_correction" else 0.5))

        sa, sb = score(a), score(b)
        margin = abs(sa - sb) / max(sa, sb)
        decision = clamp01(conflict["confidence"] * 0.6 + margin * 0.8)
        if decision < CONFLICT_GATE:
            return "queued"
        winner, loser = (a, b) if sa >= sb else (b, a)
        with self.h._lock, self.h._conn() as c:
            c.execute("UPDATE memories SET superseded_by=? WHERE id=?", (winner["id"], loser["id"]))
            self.h._ledger(c, loser["id"], "conflict_resolved",
                           {"conflictId": conflict["id"], "winner": winner["id"], "decisionConfidence": round(decision, 3)},
                           previous={"supersededBy": loser["superseded_by"]}, new={"supersededBy": winner["id"]})
        conflict["resolved"] = True
        conflict["resolution"] = "keep_a" if winner["id"] == a["id"] else "keep_b"
        return "resolved"

    autoResolve = auto_resolve  # spec spelling

    def queue(self) -> list[dict[str, Any]]:
        return [c for c in self._conflicts if not c["resolved"]]


# ----------------------------------------------------------- dreaming (spec 7)

DREAM_RELATEDNESS = 0.35
DREAM_MAX_PER_TYPE = 8


class Dreaming:
    """Proposals only; nothing becomes memory until a human approves it."""

    def __init__(self, hmem: HMEM) -> None:
        self.h = hmem
        self._proposals: dict[str, dict[str, Any]] = {}

    def _related(self, a: dict[str, Any], b: dict[str, Any]) -> float:
        return (0.5 * max(0.0, cosine(a["embedding"], b["embedding"])) + 0.2 * jaccard(a["tags"], b["tags"])
                + 0.1 * (1.0 if a["domain"] == b["domain"] else 0.0) + 0.2 * jaccard(a["entities"], b["entities"]))

    def _propose(self, ptype: str, content: str, derived: list[str]) -> dict[str, Any]:
        p = {"id": f"dream-{len(self._proposals) + 1}", "type": ptype, "content": content,
             "derivedFrom": derived, "status": "proposed"}
        self._proposals[p["id"]] = p
        with self.h._lock, self.h._conn() as c:
            self.h._ledger(c, p["id"], "dream_proposed", {"type": ptype, "derivedFrom": derived})
        return p

    def dream(self) -> list[dict[str, Any]]:
        rows = self.h._all()
        created: list[dict[str, Any]] = []
        used: set[str] = set()
        for seed in rows:
            if seed["id"] in used or sum(p["type"] == "insight" for p in created) >= DREAM_MAX_PER_TYPE:
                continue
            group = [seed] + [o for o in rows if o["id"] != seed["id"] and o["id"] not in used
                              and self._related(seed, o) >= DREAM_RELATEDNESS]
            if len(group) >= 2:
                used.update(g["id"] for g in group)
                domains = "/".join(dict.fromkeys(g["domain"] for g in group))
                created.append(self._propose("insight", f"Across {len(group)} related memories ({domains}): "
                                             + " + ".join(g["content"] for g in group), [g["id"] for g in group]))
        prefs: dict[str, list[dict[str, Any]]] = {}
        for m in rows:
            if m["type"] in ("preference", "personal") or "event:user_correction" in m["tags"]:
                prefs.setdefault(m["domain"], []).append(m)
        for domain, items in list(prefs.items())[:DREAM_MAX_PER_TYPE]:
            if len(items) >= 2:
                created.append(self._propose("invariant", f"Stable pattern in {domain}: "
                                             + "; ".join(m["content"] for m in items), [m["id"] for m in items]))
        return created

    def pending(self) -> list[dict[str, Any]]:
        return [p for p in self._proposals.values() if p["status"] == "proposed"]

    def approve(self, proposal_id: str) -> dict[str, Any] | None:
        p = self._proposals.get(proposal_id)
        if not p or p["status"] != "proposed":
            raise KeyError(f"H-MEM: no pending proposal {proposal_id}")
        p["status"] = "approved"
        with self.h._lock, self.h._conn() as c:
            self.h._ledger(c, proposal_id, "dream_approved", {"type": p["type"]})
        return self.h.add(p["content"], type="factual" if p["type"] == "insight" else "preference",
                          layer="long_term", tags=[f"dream:{p['type']}"], confidence=0.75, source="dreaming",
                          derived_from=p["derivedFrom"])

    def reject(self, proposal_id: str) -> None:
        p = self._proposals.get(proposal_id)
        if not p or p["status"] != "proposed":
            raise KeyError(f"H-MEM: no pending proposal {proposal_id}")
        p["status"] = "rejected"  # logged, not materialized
        with self.h._lock, self.h._conn() as c:
            self.h._ledger(c, proposal_id, "dream_rejected", {"type": p["type"]})


def _freq(toks: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in toks:
        out[t] = out.get(t, 0) + 1
    return out


def _row(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    d.pop("embedding", None)
    for k in ("tags", "entities", "related_to", "provenance", "derived_from"):
        d[k] = json.loads(d[k])
    return d


def reinjection(recalled: list[Recalled]) -> str:
    if not recalled:
        return ""
    by_domain: dict[str, list[Recalled]] = {}
    for rc in recalled:
        by_domain.setdefault(rc.memory["domain"], []).append(rc)
    lines = ["[MEMORY CONTEXT]"]
    abbrev = {"long_term": "LT", "working": "WK", "short_term": "ST"}
    for domain, items in by_domain.items():
        lines.append(f"## {domain}")
        for rc in items:
            m = rc.memory
            flag = " [SUPERSEDED]" if m["superseded_by"] else ""
            lines.append(
                f"- [{abbrev.get(m['layer'], 'ST')}]{flag} {m['content']} "
                f"(entities: {', '.join(m['entities'][:4])}) <{m['id']}> score={rc.relevance}"
            )
    lines.append("[/MEMORY CONTEXT]")
    return "\n".join(lines)


_hmem: HMEM | None = None


def get_hmem() -> HMEM:
    global _hmem
    if _hmem is None:
        s = get_settings()
        hash_emb = HashEmbedder()
        live = s.inference_mode != "replay" and not s.sample_mode
        emb: FallbackEmbedder | HashEmbedder
        if live and s.ai_provider == "meterless" and s.meterless_embed_model:
            emb = FallbackEmbedder(MeterlessEmbedder(s.meterless_embed_model), hash_emb)
        elif live and s.ai_provider == "nvidia" and s.hmem_use_nvidia_embedder and s.nvidia_api_key:
            emb = FallbackEmbedder(NvidiaEmbedder(s.nvidia_api_key, s.nvidia_base_url, s.embedding_model), hash_emb)
        else:
            emb = hash_emb
        _hmem = HMEM(Path(s.hmem_persist_dir) / "hmem.sqlite3", emb, s.hmem_recall_threshold)
    return _hmem
