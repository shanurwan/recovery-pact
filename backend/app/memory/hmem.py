"""Meterless H-MEM: durable, ranked, self-correcting memory for the guardians.

A port of the Meterless H-MEM contracts (github.com/Meterless/Meterless):

- memory model with layers short_term / working / long_term (weights 0.6/0.8/1.0)
- ranking, verbatim:
      raw = 0.35*semantic + 0.20*keyword + 0.10*tag + 0.10*domain
          + 0.15*entity + 0.05*layer + 0.05*recency - 0.20*superseded
      score = clamp01(raw) * confidence
- feedback deltas: helpful +0.05, not_helpful -0.03, wrong -0.20
- conflicts on the same claim key: the newer verified claim supersedes the
  older one, which is penalised in ranking but never deleted
- append-only trust ledger, enforced by SQLite triggers
- reinjection block ``[MEMORY CONTEXT] ... [/MEMORY CONTEXT]``

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
  last_accessed REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  memory_id TEXT NOT NULL,
  action TEXT NOT NULL,
  actor TEXT NOT NULL,
  details TEXT NOT NULL
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
    def __init__(self, path: str | Path, embedder: FallbackEmbedder | HashEmbedder, threshold: float) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder
        self.threshold = threshold
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _embed(self, text: str, kind: str) -> tuple[list[float], str]:
        if isinstance(self.embedder, FallbackEmbedder):
            return self.embedder.embed(text, kind)
        return self.embedder.embed(text, kind), self.embedder.name

    def _ledger(self, c: sqlite3.Connection, memory_id: str, action: str, details: dict[str, Any]) -> None:
        c.execute(
            "INSERT INTO ledger (ts, memory_id, action, actor, details) VALUES (?,?,?,?,?)",
            (time.time(), memory_id, action, "recovery-pact", json.dumps(details, default=str)),
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
    ) -> dict[str, Any]:
        tags = list(tags or [])
        if conflict_key:
            tags += [f"ck:{conflict_key}", f"verdict:{verdict}"]
        tags = list(dict.fromkeys(tags))
        ents = list(dict.fromkeys(extract_entities(content) + list(entities or [])))[:ENTITY_CAP]
        vec, emb_name = self._embed(content, "passage")
        now = time.time()
        mid = "mem-" + hashlib.sha256(f"{namespace}|{content}|{now}".encode()).hexdigest()[:16]
        related: list[str] = []
        supersedes: str | None = None
        with self._lock, self._conn() as c:
            if conflict_key:
                priors = c.execute(
                    "SELECT id, tags FROM memories WHERE namespace=? AND superseded_by IS NULL AND tags LIKE ?",
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
                            c, p["id"], "conflict_resolved", {"winner": mid, "confidence": decision}
                        )
            c.execute(
                "INSERT INTO memories (id, namespace, content, type, layer, domain, tags, entities, related_to, "
                "embedding, embedder, confidence, source, provenance, supersedes, created_at, last_accessed) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                ),
            )
            self._ledger(c, mid, "create", {"content": content, "tags": tags, "supersedes": supersedes})
        return self.get(mid) or {}

    def feedback(self, memory_id: str, verdict: str, reason: str = "") -> None:
        delta = FEEDBACK_DELTAS[verdict]
        with self._lock, self._conn() as c:
            row = c.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
            if not row:
                return
            conf = clamp01(row["confidence"] + delta)
            helpful = row["helpful_count"] + (1 if verdict == "helpful" else 0)
            tags = json.loads(row["tags"])
            if verdict == "wrong" and "review" not in tags:
                tags.append("review")
            layer = row["layer"]
            c.execute(
                "UPDATE memories SET confidence=?, helpful_count=?, tags=? WHERE id=?",
                (conf, helpful, json.dumps(tags), memory_id),
            )
            self._ledger(c, memory_id, "feedback", {"verdict": verdict, "delta": delta, "reason": reason})
            if layer == "working" and helpful >= PROMOTE_AFTER_HELPFUL:
                c.execute("UPDATE memories SET layer='long_term' WHERE id=?", (memory_id,))
                self._ledger(c, memory_id, "promote", {"from": "working", "to": "long_term"})

    # ---------------------------------------------------------------- read

    def query(
        self,
        text: str,
        *,
        namespace: str = "recovery-pact",
        tags: list[str] | None = None,
        entities: list[str] | None = None,
        top_n: int = TOP_N,
    ) -> QueryResult:
        qvec, qemb = self._embed(text, "query")
        qtoks = [t for t, _ in sorted(_freq(tokens(text)).items(), key=lambda kv: (-kv[1], -len(kv[0])))][:8]
        qtags = set(tags or [])
        qents = set(entities or []) | set(extract_entities(text))
        qdomain = classify_domain(text, list(qtags))
        now = time.time()
        with self._conn() as c:
            rows = c.execute("SELECT * FROM memories WHERE namespace=?", (namespace,)).fetchall()
        scored: list[Recalled] = []
        for r in rows:
            m = _row(r)
            content_toks = set(tokens(m["content"]))
            terms = {
                "semantic": clamp01(cosine(qvec, json.loads(r["embedding"]))) if r["embedder"] == qemb else 0.0,
                "keyword": (sum(1 for t in qtoks if t in content_toks) / len(qtoks)) if qtoks else 0.0,
                "tag": (len(qtags & set(m["tags"])) / len(qtags)) if qtags else 0.0,
                "domain": 1.0 if m["domain"] == qdomain else 0.0,
                "entity": (len(qents & set(m["entities"])) / len(qents)) if qents else 0.0,
                "layer": LAYER_WEIGHT.get(m["layer"], 0.6),
                "recency": math.exp(-((now - m["created_at"]) / 86400.0) / RECENCY_DAYS),
                "superseded": 1.0 if m["superseded_by"] else 0.0,
            }
            raw = sum(WEIGHTS[k] * v for k, v in terms.items())
            score = clamp01(raw) * m["confidence"]
            if score >= self.threshold:
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
                    self._ledger(c, rc.memory["id"], "recall", {"query": text[:200], "score": rc.relevance})
        return QueryResult(memories=top, context=reinjection(top), considered=len(rows))

    def get(self, memory_id: str) -> dict[str, Any] | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
        return _row(r) if r else None

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [_row(r) for r in rows]

    def ledger(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM ledger ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) | {"details": json.loads(r["details"])} for r in rows]

    def clear(self) -> None:
        """Wipe memory for a cold-start run. Recreates the file, ledger included."""
        with self._lock:
            if self.path.exists():
                self.path.unlink()
            with self._conn() as c:
                c.executescript(SCHEMA)


def _freq(toks: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in toks:
        out[t] = out.get(t, 0) + 1
    return out


def _row(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    d.pop("embedding", None)
    for k in ("tags", "entities", "related_to", "provenance"):
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
        if s.hmem_use_nvidia_embedder and s.nvidia_api_key and s.inference_mode != "replay":
            emb: FallbackEmbedder | HashEmbedder = FallbackEmbedder(
                NvidiaEmbedder(s.nvidia_api_key, s.nvidia_base_url, s.embedding_model), hash_emb
            )
        else:
            emb = hash_emb
        _hmem = HMEM(Path(s.hmem_persist_dir) / "hmem.sqlite3", emb, s.hmem_recall_threshold)
    return _hmem
