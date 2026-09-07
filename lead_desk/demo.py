"""One-command local story demo. No real Gemini call, no real CRM/Slack/email."""
import json
import os
import time
from pathlib import Path

from fastapi.testclient import TestClient

from .alerts import format_alert
from .app import create_app
from .models import Scoring

ROOT = Path(__file__).resolve().parents[1]


def _fact(value, evidence, confidence=1.0):
    return {"value": value, "confidence": confidence, "evidence": evidence}


class DemoScorer:
    """Scripted, grounded facts for three demo messages. Not an accuracy claim."""

    name = "demo_stub_not_accuracy"

    def score(self, message):
        lower = message.lower()
        if "8k/month" in lower:
            return Scoring.model_validate({
                "company_size_signal": _fact("15-person digital marketing agency", "15-person digital marketing agency"),
                "budget_signal": _fact("$8k/month on Meta ads", "$8k/month on Meta ads"),
                "urgency_signal": _fact("live within 2 weeks", "live within 2 weeks"),
                "intent": _fact("ready_to_buy", "urgent"), "classification": "hot", "score": 0.92,
                "reason": "Named budget, named timeline, clear buying language.",
            })
        if "just looking around" in lower:
            return Scoring.model_validate({
                "company_size_signal": {"value": None, "confidence": 0, "evidence": None},
                "budget_signal": {"value": None, "confidence": 0, "evidence": None},
                "urgency_signal": {"value": None, "confidence": 0, "evidence": None},
                "intent": _fact("researching", "just looking around"), "classification": "warm", "score": 0.7,
                "reason": "Exploratory language, no budget or timeline stated yet.",
            })
        return Scoring.model_validate({
            "company_size_signal": {"value": None, "confidence": 0, "evidence": None},
            "budget_signal": {"value": None, "confidence": 0, "evidence": None},
            "urgency_signal": {"value": None, "confidence": 0, "evidence": None},
            "intent": _fact("not_a_fit", "resume"), "classification": "cold", "score": 0.95,
            "reason": "Job applicant, not a buyer.",
        })


HOT = ("We're a 15-person digital marketing agency spending about $8k/month on Meta ads. "
       "Need a lead qualification system live within 2 weeks.")
WARM = "Just looking around at what's out there, not sure if we need this yet."
COLD = "Hi, I saw your job posting and wanted to attach my resume for the open role."


def main(database=None, output=None):
    os.environ.setdefault("LEAD_DESK_MODE", "synthetic")
    os.environ.setdefault("LEAD_DESK_OWNERS", "alice@agency.com,bob@agency.com")
    database = Path(database or ROOT / "output" / "runtime" / "demo.sqlite3")
    output = Path(output or ROOT / "output" / "demo-run.json")
    database.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    if database.exists():
        database.unlink()

    app = create_app(database, scorer=DemoScorer(), worker_enabled=True)
    stories = []
    with TestClient(app) as client:
        health = client.get("/health").json()
        if health["crm"] != "dry_run" or health["alerts"] != "dry_run" or health["autoreply"] != "dry_run":
            raise SystemExit("Demo refuses to run unless CRM/alerts/autoreply are all dry_run")
        for label, message, email in (("hot_agency", HOT, "owner@bigagency.com"),
                                       ("warm_exploring", WARM, "maybe@somefirm.com"),
                                       ("cold_job_applicant", COLD, "applicant@example.com")):
            response = client.post("/webhooks/lead/generic", json={
                "name": label.replace("_", " ").title(), "email": email, "company": None, "message": message})
            response.raise_for_status()
            event_id = response.json()["event_id"]
            deadline = time.time() + 10
            record = None
            while time.time() < deadline:
                record = next((r for r in app.state.store.records() if r["event_id"] == event_id), None)
                if record and record["state"] == "done":
                    break
                time.sleep(0.05)
            if record is None or record["state"] != "done":
                raise SystemExit(f"Demo lead {label} did not finish processing")
            result = record["result"]
            stories.append({"label": label, "message": message, "route": result["route"],
                            "assigned_owner": result["assigned_owner"],
                            "classification": (result.get("scoring") or {}).get("classification"),
                            "outbox": record["outbox"],
                            "alert_would_send": format_alert(result) if result["route"] != "cold_auto_reply" else None})

    expected_routes = {"hot_agency": "hot_assigned", "warm_exploring": "warm_assigned",
                      "cold_job_applicant": "cold_auto_reply"}
    for s in stories:
        if s["route"] != expected_routes[s["label"]]:
            raise SystemExit(f"Demo story {s['label']} did not route as expected: got {s['route']}")

    report = {"synthetic_only": True, "health": health, "stories": stories,
              "scorecard": app.state.store.scorecard(0)}
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Lead Desk local demo — synthetic only. No real Gemini, CRM, Slack, or email.")
    print()
    for s in stories:
        print(f"Lead ({s['label']}): {s['message'][:70]}...")
        print(f"  Classification: {s['classification']}  ->  Route: {s['route']}"
              + (f"  ->  Owner: {s['assigned_owner']}" if s["assigned_owner"] else ""))
        if s["alert_would_send"]:
            print(f"  Slack would say: {s['alert_would_send']}  ({s['outbox']['alert']['state']}, not actually sent)")
        print(f"  CRM write: {s['outbox']['crm']['state']}, Auto-reply: {s['outbox']['autoreply']['state']}")
        print()
    print("Scorecard (all time):", json.dumps(report["scorecard"]))
    print()
    print("Wrote " + str(output.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
