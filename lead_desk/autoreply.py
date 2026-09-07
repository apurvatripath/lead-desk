"""Polite auto-reply for cold/disqualified leads, via Resend (same provider
already used for Eagle Solectra). Dormant until LEAD_DESK_RESEND_API_KEY and
LEAD_DESK_FROM_EMAIL are configured. Never sent for hot/warm leads -- those
always go to a human first, per the plan's own scope."""
import os

import httpx

SUBJECT = "Thanks for reaching out"


def format_body(record: dict) -> str:
    name = record.get("name") or "there"
    return (f"Hi {name},\n\nThanks for getting in touch. We've received your message "
            "and someone will follow up if it's a fit for what we're currently taking on.\n\n"
            "In the meantime, feel free to reply to this email with any more detail.")


class ResendSender:
    def __init__(self):
        self.key = os.environ["LEAD_DESK_RESEND_API_KEY"]
        self.from_email = os.environ["LEAD_DESK_FROM_EMAIL"]

    def send(self, record: dict):
        if record.get("route") != "cold_auto_reply":
            return  # hot/warm/review leads always go to a human first, never auto-sent
        to = record.get("email")
        if not to:
            raise ValueError("autoreply_requires_email")
        body = {"from": self.from_email, "to": [to], "subject": SUBJECT, "text": format_body(record)}
        response = httpx.post("https://api.resend.com/emails", json=body, timeout=20,
                              headers={"Authorization": "Bearer " + self.key})
        response.raise_for_status()
