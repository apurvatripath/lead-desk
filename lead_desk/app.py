import asyncio
import hashlib
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request

from .alerts import SlackSender
from .autoreply import ResendSender
from .crm import HubSpotSender
from .outbox import process_outbox
from .routing import route
from .scoring import get_scorer
from .sources import normalize
from .store import EventConflict, Store

LOG = logging.getLogger("lead_desk")


def process_one(store, scorer, owners):
    job = store.claim()
    if job is None:
        return False
    event_id, payload, token = job
    record = route(event_id, payload, scorer, store, owners)
    store.finish(event_id, token, record.model_dump())
    LOG.info("event=%s route=%s owner=%s", event_id, record.route, record.assigned_owner)
    return True


def create_app(db_path=None, scorer=None, worker_enabled=True):
    scorer = scorer or get_scorer()
    crm_mode = os.getenv("LEAD_DESK_CRM_MODE", "dry_run")
    if crm_mode not in {"dry_run", "hubspot"}:
        raise ValueError("LEAD_DESK_CRM_MODE must be dry_run or hubspot")
    if crm_mode == "hubspot" and not os.getenv("LEAD_DESK_HUBSPOT_TOKEN"):
        raise ValueError("HubSpot CRM mode requires LEAD_DESK_HUBSPOT_TOKEN")
    alert_mode = os.getenv("ALERT_MODE", "dry_run")
    if alert_mode not in {"dry_run", "webhook"}:
        raise ValueError("ALERT_MODE must be dry_run or webhook")
    if alert_mode == "webhook" and not os.getenv("ALERT_WEBHOOK_URL"):
        raise ValueError("Webhook alerts require ALERT_WEBHOOK_URL")
    autoreply_mode = os.getenv("LEAD_DESK_AUTOREPLY_MODE", "dry_run")
    if autoreply_mode not in {"dry_run", "resend"}:
        raise ValueError("LEAD_DESK_AUTOREPLY_MODE must be dry_run or resend")
    if autoreply_mode == "resend" and (not os.getenv("LEAD_DESK_RESEND_API_KEY")
                                       or not os.getenv("LEAD_DESK_FROM_EMAIL")):
        raise ValueError("Resend auto-reply requires LEAD_DESK_RESEND_API_KEY and LEAD_DESK_FROM_EMAIL")
    owners = [o.strip() for o in os.getenv("LEAD_DESK_OWNERS", "").split(",") if o.strip()]

    store = Store(db_path or os.getenv("LEAD_DESK_DATABASE_PATH", "data/lead_desk.sqlite3"),
                  crm_enabled=crm_mode == "hubspot", alert_enabled=alert_mode == "webhook",
                  autoreply_enabled=autoreply_mode == "resend")
    senders = {"crm": HubSpotSender() if crm_mode == "hubspot" else None,
               "alert": SlackSender() if alert_mode == "webhook" else None,
               "autoreply": ResendSender() if autoreply_mode == "resend" else None}

    @asynccontextmanager
    async def lifespan(app):
        stop = asyncio.Event()

        async def worker(kind):
            while not stop.is_set():
                try:
                    if kind == "extract":
                        worked = await asyncio.to_thread(process_one, store, scorer, owners)
                    else:
                        worked = await asyncio.to_thread(process_outbox, store, kind, senders[kind])
                except Exception:
                    # Durable lease/row makes the job available again later.
                    LOG.error("Worker/storage error; durable job retained")
                    worked = False
                if not worked:
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=0.25)
                    except TimeoutError:
                        pass

        tasks = []
        if worker_enabled:
            tasks.append(asyncio.create_task(worker("extract")))
            for kind in ("crm", "alert", "autoreply"):
                if senders[kind]:
                    tasks.append(asyncio.create_task(worker(kind)))
        yield
        stop.set()
        for t in tasks:
            await t

    app = FastAPI(title="Lead Desk", lifespan=lifespan)
    app.state.store = store
    app.state.scorer = scorer

    @app.post("/webhooks/lead/{source}")
    async def lead_webhook(source: str, request: Request):
        try:
            raw = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON body")
        if not isinstance(raw, dict):
            raise HTTPException(400, "Body must be a JSON object")
        normalized = normalize(source, raw)
        if not (normalized.get("email") or normalized.get("phone")):
            raise HTTPException(422, "Lead needs at least an email or a phone number")
        now = datetime.now(timezone.utc).isoformat()
        content_hash = hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()
        submission_id = request.headers.get("X-Lead-Desk-Submission-Id")
        event_id = submission_id or ("lead-" + content_hash[:32])
        synthetic = os.getenv("LEAD_DESK_MODE", "synthetic") == "synthetic"
        full_payload = {**normalized, "source": source, "received_at": now, "synthetic": synthetic}
        try:
            canonical_id, created = store.accept(event_id, content_hash, full_payload)
        except EventConflict:
            raise HTTPException(409, "This submission id or identical content was already used differently")
        return {"event_id": canonical_id, "duplicate": not created}

    @app.get("/health")
    def health():
        return {"status": "ok", "crm": crm_mode, "alerts": alert_mode, "autoreply": autoreply_mode,
                "scorer": scorer.name, "owners": len(owners), "queue": store.counts()}

    @app.get("/scorecard")
    def scorecard(days: int = 7):
        return store.scorecard(time.time() - days * 86400)

    @app.get("/leads/{event_id}")
    def get_lead(event_id: str):
        record = next((r for r in store.records() if r["event_id"] == event_id), None)
        if record is None:
            raise HTTPException(404, "Unknown event_id")
        return record

    return app
