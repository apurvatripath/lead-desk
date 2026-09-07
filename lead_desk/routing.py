from .models import LeadRecord
from .scoring import ScoringFailure

CONFIDENCE_THRESHOLD = 0.6


def route(event_id: str, payload: dict, scorer, store, owners: list[str]) -> LeadRecord:
    reasons = []
    scoring = None
    try:
        message = payload.get("message", "").strip()
        if not message:
            raise ScoringFailure("empty_message")
        scoring = scorer.score(message)
        if scoring.score < CONFIDENCE_THRESHOLD:
            reasons.append("low_confidence_classification")
    except ScoringFailure as exc:
        reasons.append(str(exc))
    except Exception:
        reasons.append("unexpected_scoring_failure")

    assigned_owner = None
    if reasons or scoring is None:
        destination = "needs_human_review"
    elif scoring.classification in ("hot", "warm"):
        destination = "hot_assigned" if scoring.classification == "hot" else "warm_assigned"
        assigned_owner = store.next_owner(owners) if owners else None
        if assigned_owner is None:
            reasons.append("no_owners_configured")
            destination = "needs_human_review"
    else:
        destination = "cold_auto_reply"

    return LeadRecord(event_id=event_id, source=payload.get("source", "unknown"),
                      name=payload.get("name"), email=payload.get("email"), phone=payload.get("phone"),
                      company=payload.get("company"), role=payload.get("role"),
                      message=payload.get("message", ""), received_at=payload["received_at"],
                      scoring=scoring, route=destination, assigned_owner=assigned_owner,
                      review_reasons=reasons, scorer=scorer.name, synthetic=payload.get("synthetic", True))
