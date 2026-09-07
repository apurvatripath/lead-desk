"""HubSpot CRM writer. Dormant until LEAD_DESK_HUBSPOT_TOKEN is configured.

Uses the batch upsert-by-email endpoint so a retried write never creates a
duplicate contact -- the same idempotency posture as everything else built
tonight. Only ever writes standard properties guaranteed to exist on any
HubSpot portal (email/firstname/lastname/phone/company); score/classification
are attempted as custom properties and dropped automatically on the one retry
if the portal doesn't have them configured, rather than failing the whole
write over an optional field.
"""
import os

import httpx

BASE = "https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert"


def _split_name(name):
    if not name:
        return "", ""
    parts = name.strip().split(" ", 1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def _properties(record: dict, with_custom: bool) -> dict:
    first, last = _split_name(record.get("name"))
    props = {"firstname": first, "lastname": last, "phone": record.get("phone") or "",
             "company": record.get("company") or ""}
    if with_custom:
        scoring = record.get("scoring") or {}
        props["lead_desk_score"] = str(scoring.get("score", ""))
        props["lead_desk_classification"] = scoring.get("classification", "")
    return props


class HubSpotSender:
    def __init__(self):
        self.token = os.environ["LEAD_DESK_HUBSPOT_TOKEN"]

    def send(self, record: dict):
        email = record.get("email")
        if not email:
            raise ValueError("hubspot_requires_email")
        for with_custom in (True, False):
            body = {"inputs": [{"idProperty": "email", "id": email,
                                "properties": _properties(record, with_custom)}]}
            response = httpx.post(BASE, json=body, timeout=20,
                                  headers={"Authorization": "Bearer " + self.token})
            if response.status_code < 300:
                return
            if with_custom and response.status_code == 400 and "PROPERTY" in response.text.upper():
                continue  # retry once without the optional custom properties
            response.raise_for_status()
