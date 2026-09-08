import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

MAX_OUTBOX_ATTEMPTS = 5


class EventConflict(Exception):
    pass


class Store:
    def __init__(self, path: str | Path, crm_enabled=False, alert_enabled=False, autoreply_enabled=False):
        self.path = str(path)
        self.enabled = {"crm": crm_enabled, "alert": alert_enabled, "autoreply": autoreply_enabled}
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS leads (
                    id TEXT PRIMARY KEY, identity TEXT NOT NULL UNIQUE, payload TEXT NOT NULL,
                    state TEXT NOT NULL, created REAL NOT NULL,
                    lease_until REAL, lease_token TEXT, result TEXT
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    event_id TEXT NOT NULL, kind TEXT NOT NULL, state TEXT NOT NULL,
                    updated REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, reason TEXT,
                    PRIMARY KEY(event_id, kind)
                );
                CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, val TEXT NOT NULL);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def accept(self, event_id: str, identity: str, payload: dict) -> tuple[str, bool]:
        """Atomically save the raw lead. Returns (canonical_event_id, created).
        Same id + same content -> (that id, False). Same id + different content ->
        conflict (a caller reused an id incorrectly). Different id + identical
        content (identity hash) -> dedupes to the existing canonical id, same as
        Project 2's SHA-256 dedup: repeat submissions never create a second row,
        even under a new id."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT id,identity FROM leads WHERE id=?", (event_id,)).fetchone()
            if previous:
                if previous["identity"] != identity:
                    raise EventConflict()
                return event_id, False
            same_identity = db.execute("SELECT id FROM leads WHERE identity=?", (identity,)).fetchone()
            if same_identity:
                return same_identity["id"], False
            db.execute("INSERT INTO leads (id,identity,payload,state,created) VALUES (?,?,?,?,?)",
                      (event_id, identity, json.dumps(payload, sort_keys=True), "pending", time.time()))
            return event_id, True

    def claim(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            now = time.time()
            row = db.execute("SELECT * FROM leads WHERE state='pending' OR "
                             "(state='processing' AND lease_until < ?) ORDER BY created LIMIT 1", (now,)).fetchone()
            if row is None:
                return None
            token = str(uuid.uuid4())
            db.execute("UPDATE leads SET state='processing',lease_until=?,lease_token=? WHERE id=?",
                      (now + 180, token, row["id"]))
            return row["id"], json.loads(row["payload"]), token

    def finish(self, event_id: str, token: str, result: dict):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute("UPDATE leads SET state='done',result=?,lease_until=NULL,lease_token=NULL "
                                "WHERE id=? AND lease_token=?", (json.dumps(result), event_id, token))
            if cursor.rowcount:
                for kind in ("crm", "alert", "autoreply"):
                    db.execute("INSERT INTO outbox VALUES (?,?,?,?,0,NULL)",
                              (event_id, kind, "pending" if self.enabled[kind] else "dry_run", time.time()))

    def claim_outbox(self, kind: str):
        """Every finished lead gets exactly one row per outbox kind. A duplicate CRM
        write/alert/email is harmless (idempotent upsert or a second notice), so
        failures retry automatically instead of freezing for human review."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            now = time.time()
            db.execute("UPDATE outbox SET state='pending' WHERE kind=? AND state='sending' AND updated < ?",
                      (kind, now - 120))
            row = db.execute("SELECT o.event_id,l.result FROM outbox o JOIN leads l ON l.id=o.event_id "
                             "WHERE o.kind=? AND o.state='pending' ORDER BY l.created LIMIT 1", (kind,)).fetchone()
            if row is None:
                return None
            db.execute("UPDATE outbox SET state='sending',updated=? WHERE event_id=? AND kind=?",
                      (now, row["event_id"], kind))
            return row["event_id"], json.loads(row["result"])

    def finish_outbox(self, event_id: str, kind: str, sent: bool, reason=None):
        with self.connection() as db:
            if sent:
                db.execute("UPDATE outbox SET state='sent',updated=?,reason=NULL WHERE event_id=? AND kind=? AND state='sending'",
                          (time.time(), event_id, kind))
                return
            row = db.execute("SELECT attempts FROM outbox WHERE event_id=? AND kind=?", (event_id, kind)).fetchone()
            attempts = row["attempts"] + 1
            state = "failed" if attempts >= MAX_OUTBOX_ATTEMPTS else "pending"
            db.execute("UPDATE outbox SET state=?,attempts=?,updated=?,reason=? WHERE event_id=? AND kind=? AND state='sending'",
                      (state, attempts, time.time(), reason, event_id, kind))

    def next_owner(self, owners: list[str]) -> str:
        """Durable round-robin: the rotation index survives restarts."""
        if not owners:
            raise ValueError("No owners configured for round-robin assignment")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT val FROM settings WHERE name='owner_rotation'").fetchone()
            index = int(row["val"]) if row else 0
            owner = owners[index % len(owners)]
            db.execute("INSERT INTO settings VALUES ('owner_rotation',?) "
                      "ON CONFLICT(name) DO UPDATE SET val=excluded.val", (str(index + 1),))
            return owner

    def records(self):
        with self.connection() as db:
            leads = db.execute("SELECT * FROM leads ORDER BY created").fetchall()
            outbox = db.execute("SELECT * FROM outbox").fetchall()
            by_lead = {}
            for row in outbox:
                by_lead.setdefault(row["event_id"], {})[row["kind"]] = {
                    "state": row["state"], "attempts": row["attempts"], "reason": row["reason"]}
            return [{"event_id": r["id"], "state": r["state"],
                     "result": json.loads(r["result"]) if r["result"] else None,
                     "outbox": by_lead.get(r["id"], {})} for r in leads]

    def counts(self):
        with self.connection() as db:
            return dict(db.execute("SELECT state,COUNT(*) FROM leads GROUP BY state").fetchall())

    def scorecard(self, since: float = 0):
        """Weekly scorecard: leads in / qualified / by source / by classification."""
        with self.connection() as db:
            rows = db.execute("SELECT result FROM leads WHERE state='done' AND created >= ?", (since,)).fetchall()
        results = [json.loads(r["result"]) for r in rows]
        by_source, by_classification = {}, {}
        for r in results:
            by_source[r["source"]] = by_source.get(r["source"], 0) + 1
            cls = (r.get("scoring") or {}).get("classification", "unscored")
            by_classification[cls] = by_classification.get(cls, 0) + 1
        qualified = sum(1 for r in results if r["route"] in ("hot_assigned", "warm_assigned"))
        return {"leads_in": len(results), "qualified": qualified,
                "needs_review": sum(1 for r in results if r["route"] == "needs_human_review"),
                "by_source": by_source, "by_classification": by_classification}
