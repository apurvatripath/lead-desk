"""Generic durable outbox processor shared by crm.py, alerts.py and autoreply.py.
Every finished lead gets exactly one row per kind (see store.finish); a failed send
retries automatically since none of these three sends have a customer-facing
double-send risk the way a duplicate SMS would."""


def process_outbox(store, kind: str, sender):
    job = store.claim_outbox(kind)
    if job is None:
        return False
    event_id, record = job
    try:
        sender.send(record)
        store.finish_outbox(event_id, kind, sent=True)
    except Exception as exc:
        store.finish_outbox(event_id, kind, sent=False, reason=type(exc).__name__)
    return True
