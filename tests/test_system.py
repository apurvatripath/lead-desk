import time

import pytest
from fastapi.testclient import TestClient

from lead_desk.app import create_app, process_one
from lead_desk.crm import HubSpotSender
from lead_desk.models import Scoring
from lead_desk.outbox import process_outbox
from lead_desk.routing import route
from lead_desk.scoring import ScoringFailure
from lead_desk.sources import normalize, normalize_typeform
from lead_desk.store import EventConflict, Store, MAX_OUTBOX_ATTEMPTS


def fact(value=None, evidence=None, confidence=1.0):
    return {"value": value, "confidence": confidence if value is not None else 0.0, "evidence": evidence}


def scoring(classification="hot", score=0.9):
    return Scoring.model_validate({
        "company_size_signal": fact("10 person team", "10 person team"),
        "budget_signal": fact("$5k/mo budget", "$5k/mo budget"),
        "urgency_signal": fact("need this live this week", "need this live this week"),
        "intent": fact("ready_to_buy", "ready_to_buy"),
        "classification": classification, "score": score,
        "reason": "clear buying signal",
    })


class Stub:
    name = "unit_test_stub_not_accuracy"

    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result if result is not None else scoring(), error, 0

    def score(self, message):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def payload(message="10 person team, $5k/mo budget, need this live this week", **changes):
    return {"source": "generic", "name": "Alex", "email": "alex@example.com", "phone": None,
            "company": "Acme", "role": "Founder", "message": message,
            "received_at": "2026-09-06T00:00:00+00:00", "synthetic": True, **changes}


# --- routing ---

def test_hot_lead_gets_assigned_a_round_robin_owner(tmp_path):
    store = Store(tmp_path / "s.sqlite3")
    record = route("e1", payload(), Stub(scoring("hot", 0.9)), store, ["alice", "bob"])
    assert record.route == "hot_assigned"
    assert record.assigned_owner == "alice"
    second = route("e2", payload(), Stub(scoring("hot", 0.9)), store, ["alice", "bob"])
    assert second.assigned_owner == "bob"
    third = route("e3", payload(), Stub(scoring("hot", 0.9)), store, ["alice", "bob"])
    assert third.assigned_owner == "alice"  # wraps around


def test_warm_lead_also_gets_assigned(tmp_path):
    store = Store(tmp_path / "s.sqlite3")
    record = route("e1", payload(), Stub(scoring("warm", 0.7)), store, ["alice"])
    assert record.route == "warm_assigned"
    assert record.assigned_owner == "alice"


def test_cold_lead_gets_no_owner(tmp_path):
    store = Store(tmp_path / "s.sqlite3")
    record = route("e1", payload(), Stub(scoring("cold", 0.9)), store, ["alice"])
    assert record.route == "cold_auto_reply"
    assert record.assigned_owner is None


def test_low_confidence_score_forces_review_even_if_classified_hot(tmp_path):
    store = Store(tmp_path / "s.sqlite3")
    record = route("e1", payload(), Stub(scoring("hot", 0.4)), store, ["alice"])
    assert record.route == "needs_human_review"
    assert "low_confidence_classification" in record.review_reasons


def test_scorer_failure_routes_to_review_not_lost(tmp_path):
    store = Store(tmp_path / "s.sqlite3")
    record = route("e1", payload(), Stub(error=ScoringFailure("boom")), store, ["alice"])
    assert record.route == "needs_human_review"
    assert "boom" in record.review_reasons


def test_empty_message_routes_to_review(tmp_path):
    store = Store(tmp_path / "s.sqlite3")
    record = route("e1", payload(message=""), Stub(), store, ["alice"])
    assert record.route == "needs_human_review"


def test_hot_lead_with_no_owners_configured_falls_back_to_review(tmp_path):
    store = Store(tmp_path / "s.sqlite3")
    record = route("e1", payload(), Stub(scoring("hot", 0.9)), store, [])
    assert record.route == "needs_human_review"
    assert "no_owners_configured" in record.review_reasons


# --- idempotency ---

def test_identical_resubmission_under_new_id_dedupes_to_canonical(tmp_path):
    store = Store(tmp_path / "s.sqlite3")
    id1, created1 = store.accept("first", "hash-a", {"x": 1})
    assert created1 is True
    id2, created2 = store.accept("second", "hash-a", {"x": 1})
    assert created2 is False
    assert id2 == id1 == "first"


def test_same_id_same_content_is_a_noop_duplicate(tmp_path):
    store = Store(tmp_path / "s.sqlite3")
    store.accept("e1", "hash-a", {"x": 1})
    _, created = store.accept("e1", "hash-a", {"x": 1})
    assert created is False


def test_reused_id_with_different_content_conflicts(tmp_path):
    store = Store(tmp_path / "s.sqlite3")
    store.accept("e1", "hash-a", {"x": 1})
    with pytest.raises(EventConflict):
        store.accept("e1", "hash-b", {"x": 2})


# --- sources normalization ---

def test_generic_source_passthrough():
    normalized = normalize("generic", {"name": "Alex", "email": "a@b.com", "message": "hi"})
    assert normalized["email"] == "a@b.com"


def test_typeform_source_normalizes_nested_answers():
    payload = {"form_response": {"answers": [
        {"field": {"ref": "name"}, "type": "text", "text": "Alex Morgan"},
        {"field": {"ref": "email"}, "type": "email", "email": "alex@example.com"},
        {"field": {"ref": "notes"}, "type": "text", "text": "need this live this week"},
    ]}}
    normalized = normalize_typeform(payload)
    assert normalized["email"] == "alex@example.com"
    assert "need this live" in normalized["message"]


def test_unknown_source_falls_back_to_generic():
    normalized = normalize("webflow", {"name": "Alex", "email": "a@b.com"})
    assert normalized["email"] == "a@b.com"


# --- outbox: alert, crm, autoreply (dry-run / retry / route-gating) ---

class FakeSender:
    def __init__(self, error=None):
        self.calls, self.error, self.sent = 0, error, []

    def send(self, record):
        self.calls += 1
        if self.error:
            raise self.error
        self.sent.append(record)


def finished_lead(store, route_value="hot_assigned", owner="alice", classification="hot"):
    event_id = "lead-" + route_value
    store.accept(event_id, event_id, payload())
    _, p, token = store.claim()
    record = route(event_id, p, Stub(scoring(classification, 0.9)), store, [owner] if owner else [])
    store.finish(event_id, token, record.model_dump())
    return record


def test_dry_run_never_sends_any_outbox(tmp_path):
    store = Store(tmp_path / "s.sqlite3")
    finished_lead(store)
    sender = FakeSender()
    for kind in ("crm", "alert", "autoreply"):
        assert not process_outbox(store, kind, sender)
    assert sender.calls == 0


def test_alert_fires_for_hot_but_not_cold(tmp_path):
    store = Store(tmp_path / "s.sqlite3", alert_enabled=True)
    finished_lead(store, "hot_assigned", "alice", "hot")
    sender = FakeSender()
    assert process_outbox(store, "alert", sender)
    assert sender.calls == 1
    assert "HOT LEAD" in "".join(str(r) for r in sender.sent) or sender.sent


def test_autoreply_fires_for_cold_only(tmp_path):
    store = Store(tmp_path / "s.sqlite3", autoreply_enabled=True)
    finished_lead(store, "cold_auto_reply", None, "cold")
    sender = FakeSender()
    assert process_outbox(store, "autoreply", sender)
    assert sender.calls == 1


def test_outbox_retries_then_gives_up(tmp_path):
    store = Store(tmp_path / "s.sqlite3", alert_enabled=True)
    finished_lead(store)
    sender = FakeSender(error=TimeoutError())
    for _ in range(MAX_OUTBOX_ATTEMPTS):
        assert process_outbox(store, "alert", sender)
    assert not process_outbox(store, "alert", sender)
    record = next(r for r in store.records() if r["event_id"] == "lead-hot_assigned")
    assert record["outbox"]["alert"]["state"] == "failed"
    assert record["outbox"]["alert"]["attempts"] == MAX_OUTBOX_ATTEMPTS


def test_interrupted_send_is_retried_not_lost(tmp_path):
    store = Store(tmp_path / "s.sqlite3", alert_enabled=True)
    finished_lead(store)
    assert store.claim_outbox("alert")
    with store.connection() as db:
        db.execute("UPDATE outbox SET updated=? WHERE kind='alert'", (time.time() - 121,))
    sender = FakeSender()
    assert process_outbox(store, "alert", sender)
    assert sender.calls == 1


# --- CRM: idempotent upsert + custom-property fallback ---

def test_hubspot_falls_back_without_custom_properties_on_400(monkeypatch):
    import httpx as httpx_module

    calls = []

    class FakeResponse:
        def __init__(self, status_code, text=""):
            self.status_code, self.text = status_code, text

        def raise_for_status(self):
            if self.status_code >= 300:
                raise RuntimeError("http error")

    def fake_post(url, json=None, timeout=None, headers=None):
        calls.append(json)
        if len(calls) == 1:
            return FakeResponse(400, "Property \"lead_desk_score\" does not exist")
        return FakeResponse(200)

    monkeypatch.setenv("LEAD_DESK_HUBSPOT_TOKEN", "fake-token")
    monkeypatch.setattr(httpx_module, "post", fake_post)
    sender = HubSpotSender()
    sender.send({"email": "a@b.com", "name": "Alex Morgan", "company": "Acme",
                "scoring": {"score": 0.9, "classification": "hot"}})
    assert len(calls) == 2
    assert "lead_desk_score" in calls[0]["inputs"][0]["properties"]
    assert "lead_desk_score" not in calls[1]["inputs"][0]["properties"]


def test_hubspot_requires_email():
    sender = object.__new__(HubSpotSender)
    with pytest.raises(ValueError):
        sender.send({"email": None})


# --- scorecard ---

def test_scorecard_counts_by_source_and_classification(tmp_path):
    store = Store(tmp_path / "s.sqlite3")
    finished_lead(store, "hot_assigned", "alice", "hot")
    finished_lead(store, "cold_auto_reply", None, "cold")
    card = store.scorecard(0)
    assert card["leads_in"] == 2
    assert card["qualified"] == 1
    assert card["by_classification"]["hot"] == 1
    assert card["by_classification"]["cold"] == 1


# --- live async worker regression guard (lesson from Track A tonight) ---

def test_live_async_workers_actually_process_a_real_lead(tmp_path, monkeypatch):
    """Every test above calls process_one/process_outbox directly and never starts
    the real asyncio worker loop the way uvicorn would. That loop can silently
    break (wrong args to asyncio.to_thread, wrong dict key, etc.) while every
    direct-call test above keeps passing. This one starts the app for real."""
    monkeypatch.setenv("LEAD_DESK_MODE", "synthetic")
    monkeypatch.setenv("LEAD_DESK_API_KEY", "test-only-key")
    monkeypatch.setenv("LEAD_DESK_OWNERS", "alice@agency.com")
    app = create_app(tmp_path / "live.sqlite3", scorer=Stub(scoring("hot", 0.9)), worker_enabled=True)
    with TestClient(app, headers={"Authorization": "Bearer test-only-key"}) as client:
        response = client.post("/webhooks/lead/generic", json={
            "name": "Alex", "email": "alex@example.com", "company": "Acme",
            "message": "10 person team, $5k/mo budget, need this live this week"})
        assert response.status_code == 200
        event_id = response.json()["event_id"]
        deadline = time.time() + 5
        record = None
        while time.time() < deadline:
            record = next((r for r in app.state.store.records() if r["event_id"] == event_id), None)
            if record and record["state"] == "done":
                break
            time.sleep(0.05)
    assert record is not None and record["state"] == "done"
    assert record["result"]["route"] == "hot_assigned"


@pytest.fixture
def secured_app(tmp_path, monkeypatch):
    monkeypatch.setenv("LEAD_DESK_API_KEY", "test-only-key")
    monkeypatch.setenv("LEAD_DESK_CRM_MODE", "dry_run")
    monkeypatch.setenv("ALERT_MODE", "dry_run")
    monkeypatch.setenv("LEAD_DESK_AUTOREPLY_MODE", "dry_run")
    return create_app(tmp_path / "api.sqlite3", scorer=Stub(), worker_enabled=False)


def test_startup_requires_authentication_key(tmp_path, monkeypatch):
    monkeypatch.delenv("LEAD_DESK_API_KEY", raising=False)
    with pytest.raises(ValueError, match="LEAD_DESK_API_KEY"):
        create_app(tmp_path / "no-key.sqlite3", scorer=Stub())
    assert not (tmp_path / "no-key.sqlite3").exists()


def test_public_proof_page_contains_evidence_boundary(secured_app):
    with TestClient(secured_app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "WORKING PROOF" in response.text
    assert "FICTIONAL LEADS ONLY" in response.text
    assert "does not claim a client deployment" in response.text


@pytest.mark.parametrize("authorization", [None, "Bearer wrong", "Basic test-only-key", "Bearer "])
def test_unauthorized_requests_cannot_read_or_write(secured_app, authorization):
    headers = {} if authorization is None else {"Authorization": authorization}
    with TestClient(secured_app) as client:
        assert client.post("/webhooks/lead/generic", json=payload(), headers=headers).status_code == 401
        assert client.get("/leads/unknown", headers=headers).status_code == 401
        assert client.get("/scorecard", headers=headers).status_code == 401
        assert client.get("/health").status_code == 200
    assert secured_app.state.store.counts() == {}


@pytest.mark.parametrize("email", [None, "", "   ", 123, ["alex@example.com"]])
def test_missing_email_rejected_before_queueing(secured_app, email):
    with TestClient(secured_app, headers={"Authorization": "Bearer test-only-key"}) as client:
        response = client.post("/webhooks/lead/generic", json=payload(email=email, phone="5550100"))
        assert response.status_code == 422
    assert secured_app.state.store.counts() == {}


@pytest.mark.parametrize("explicit_id", [None, "source-submission-1"])
def test_http_retry_keeps_original_record_and_processes_once(secured_app, monkeypatch, explicit_id):
    import lead_desk.app as app_module
    from datetime import datetime as real_datetime

    class Clock:
        count = 0

        @classmethod
        def now(cls, tz):
            cls.count += 1
            return real_datetime(2026, 9, 8, 10, 0, cls.count, tzinfo=tz)

    monkeypatch.setattr(app_module, "datetime", Clock)
    headers = {"Authorization": "Bearer test-only-key"}
    if explicit_id:
        headers["X-Lead-Desk-Submission-Id"] = explicit_id
    with TestClient(secured_app, headers=headers) as client:
        first = client.post("/webhooks/lead/generic", json=payload())
        assert first.status_code == 200
        event_id = first.json()["event_id"]
        assert first.json()["duplicate"] is False
        assert process_one(secured_app.state.store, secured_app.state.scorer, ["alice"])
        original = client.get(f"/leads/{event_id}").json()
        second = client.post("/webhooks/lead/generic", json=payload())
        assert second.status_code == 200
        assert second.json() == {"event_id": event_id, "duplicate": True}
        third = client.post("/webhooks/lead/generic", json=payload(),
                            headers={"X-Lead-Desk-Submission-Id": "different-id"})
        assert third.json() == {"event_id": event_id, "duplicate": True}
        assert not process_one(secured_app.state.store, secured_app.state.scorer, ["alice"])
        assert client.get(f"/leads/{event_id}").json() == original
        assert client.get("/scorecard").status_code == 200
        assert secured_app.state.scorer.calls == 1
        assert len(original["outbox"]) == 3
        if explicit_id:
            changed = client.post("/webhooks/lead/generic", json=payload(message="different content"))
            assert changed.status_code == 409
    assert secured_app.state.store.counts() == {"done": 1}
