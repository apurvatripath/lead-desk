import json
import os
import time
from typing import Protocol

import httpx

from .models import PROMPT, Scoring

SCHEMA = {
    "type": "object",
    "properties": {
        "company_size_signal": {"type": "object", "properties": {
            "value": {"type": ["string", "null"]}, "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence": {"type": ["string", "null"]}}, "required": ["value", "confidence", "evidence"]},
        "budget_signal": {"type": "object", "properties": {
            "value": {"type": ["string", "null"]}, "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence": {"type": ["string", "null"]}}, "required": ["value", "confidence", "evidence"]},
        "urgency_signal": {"type": "object", "properties": {
            "value": {"type": ["string", "null"]}, "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence": {"type": ["string", "null"]}}, "required": ["value", "confidence", "evidence"]},
        "intent": {"type": "object", "properties": {
            "value": {"type": ["string", "null"], "enum": ["ready_to_buy", "researching", "not_a_fit", None]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence": {"type": ["string", "null"]}}, "required": ["value", "confidence", "evidence"]},
        "classification": {"type": "string", "enum": ["hot", "warm", "cold"]},
        "score": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string"},
    },
    "required": ["company_size_signal", "budget_signal", "urgency_signal", "intent", "classification", "score", "reason"],
}


class ScoringFailure(Exception):
    """Safe public error code, never provider response bodies or credentials."""


class Scorer(Protocol):
    name: str

    def score(self, message: str) -> Scoring: ...


def validate(raw: str, message: str) -> Scoring:
    try:
        result = Scoring.model_validate_json(raw)
        for field in ("company_size_signal", "budget_signal", "urgency_signal", "intent"):
            fact = getattr(result, field)
            if fact.evidence is not None and fact.evidence not in message:
                raise ValueError("Ungrounded evidence")
        return result
    except (ValueError, TypeError) as exc:
        raise ScoringFailure("invalid_or_ungrounded_output") from exc


class GeminiScorer:
    def __init__(self):
        self.model = os.getenv("LEAD_DESK_GEMINI_MODEL", "gemini-3.6-flash")
        self.name = "gemini/" + self.model

    def score(self, message: str) -> Scoring:
        key = os.getenv("LEAD_DESK_GEMINI_API_KEY", "")
        if not key:
            raise ScoringFailure("scorer_not_configured")
        body = {
            "systemInstruction": {"parts": [{"text": PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": message}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 2048,
                                  "responseMimeType": "application/json", "responseJsonSchema": SCHEMA},
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        delay = 0.5
        for attempt in range(3):
            try:
                response = httpx.post(url, json=body, timeout=45, headers={"x-goog-api-key": key})
            except httpx.TransportError as exc:
                if attempt == 2:
                    raise ScoringFailure("scorer_unavailable") from exc
                time.sleep(delay)
                delay *= 2
                continue
            if response.status_code != 200:
                retryable = response.status_code in (408, 429) or response.status_code >= 500
                if not retryable or attempt == 2:
                    raise ScoringFailure(f"scorer_http_{response.status_code}")
                retry_after = 0
                try:
                    retry_after = min(30, int(response.headers.get("Retry-After", 0)))
                except ValueError:
                    pass
                time.sleep(max(retry_after, delay))
                delay *= 2
                continue
            data = response.json()
            candidate = data.get("candidates", [{}])[0]
            if candidate.get("finishReason") != "STOP":
                if attempt == 2:
                    raise ScoringFailure("scorer_incomplete_response")
                time.sleep(delay)
                delay *= 2
                continue
            text = "".join(p.get("text", "") for p in candidate.get("content", {}).get("parts", [])
                           if not p.get("thought"))
            return validate(text, message)
        raise ScoringFailure("scorer_unavailable")


def get_scorer() -> Scorer:
    provider = os.getenv("LEAD_DESK_SCORER_PROVIDER", "gemini")
    if provider == "gemini":
        return GeminiScorer()
    raise ValueError("LEAD_DESK_SCORER_PROVIDER must be gemini")
