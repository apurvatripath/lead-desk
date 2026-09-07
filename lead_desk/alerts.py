"""Owner-facing Slack alert. Dormant until ALERT_WEBHOOK_URL is configured, same
pattern as Track A. Works with any Slack/Discord/custom incoming-webhook URL."""
import os

import httpx


def format_alert(record: dict) -> str:
    route = record.get("route")
    scoring = record.get("scoring") or {}
    who = record.get("name") or record.get("email") or record.get("phone") or "unknown lead"
    company = f" ({record['company']})" if record.get("company") else ""
    reason = scoring.get("reason", "")
    if route == "hot_assigned":
        return (f"HOT LEAD: {who}{company} -> assigned to {record.get('assigned_owner')}. "
                f"{reason} Source: {record.get('source')}.")
    if route == "warm_assigned":
        return (f"New lead: {who}{company} -> assigned to {record.get('assigned_owner')}. "
                f"{reason} Source: {record.get('source')}.")
    reasons = ", ".join(record.get("review_reasons") or []) or "unclear signal"
    return f"Needs a human look: {who}{company} ({reasons}). Source: {record.get('source')}."


class SlackSender:
    def __init__(self):
        self.url = os.environ["ALERT_WEBHOOK_URL"]

    def send(self, record: dict):
        if record.get("route") == "cold_auto_reply":
            return  # no human needed for a disqualified lead, per plan scope
        text = format_alert(record)
        response = httpx.post(self.url, json={"text": text, "content": text}, timeout=15)
        response.raise_for_status()
