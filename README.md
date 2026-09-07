# Lead Desk

**No real Gemini call, CRM, Slack, or email is connected by default. Every write is dry-run until you configure a real credential.** This proves the routing/scoring/idempotency logic against synthetic input; nothing here has been run against a real client's leads, CRM, or Slack workspace.

Built from `Lead_Desk_Business_Plan.docx` (v1.0, 6 September 2026) — a productized inbound-lead qualification and routing service for 5-25 person marketing agencies. This is the v1 scope from that plan: one normalized inbound source, AI scoring against an ICP rubric, CRM write, round-robin owner assignment, Slack alert, auto-reply for disqualified leads, and a weekly scorecard.

A FastAPI webhook receives one inbound lead, a durable SQLite worker scores it against an ICP rubric via a live Gemini call, then routes it: **hot/warm leads** get a round-robin owner assignment + a CRM write + a Slack alert; **cold leads** get a polite auto-reply and nothing else; anything the scorer can't confidently classify goes to **human review** instead of silently guessing.

## Run locally (PowerShell)

```powershell
Set-Location D:\Apurva\lead-desk
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
$env:LEAD_DESK_MODE = 'synthetic'
$env:LEAD_DESK_OWNERS = 'alice@agency.com,bob@agency.com'
.\.venv\Scripts\python.exe -m uvicorn lead_desk.app:create_app --factory --host 127.0.0.1 --port 8092
```

`GET http://127.0.0.1:8092/health` reports mode for each channel (CRM/alerts/autoreply) and queue counts. `/docs` lists routes.

## One-command local demo (no server, no real Gemini/CRM/Slack/email)

```powershell
Set-Location D:\Apurva\lead-desk
$env:PYTHONPATH = '.'
.\.venv\Scripts\python.exe -m lead_desk.demo
```

Runs three scripted stories (a clearly hot agency lead, a warm exploratory lead, a cold job-applicant message) through the real routing/round-robin/outbox logic and prints what each channel would have sent. Writes `output/demo-run.json`. Uses a scripted scorer for those three messages only, not a real Gemini call.

## Webhook contract

`POST /webhooks/lead/{source}` — JSON body, one lead. `{source}` is `generic` for any platform already mapped to the canonical shape (`name`, `email`, `phone`, `company`, `role`, `message`) — in practice this covers Meta Lead Ads, Google Lead Forms, Webflow, and GoHighLevel forms, since each of those is configured at setup time (via their own native webhook or a Zapier/Make passthrough) to POST that shape directly; no per-platform code is needed for that path. `typeform` has a genuine bespoke normalizer (`lead_desk/sources.py`) since Typeform's raw webhook shape is a nested answers-by-type structure, not a flat object — proof this isn't just one hardcoded form. Adding a new source is a new `normalize_*` function in `sources.py`, no other file changes.

An optional `X-Lead-Desk-Submission-Id` header sets the idempotency key explicitly; otherwise it's derived from a SHA-256 hash of the normalized content. **Repeat content is always deduplicated to the same canonical record, even under a different id** — matching Project 2's dedup semantics exactly. Reusing an id for genuinely different content returns HTTP 409.

Lead needs at least an email or a phone (422 otherwise).

## Scoring and routing

`lead_desk/scoring.py` calls Gemini (`LEAD_DESK_GEMINI_API_KEY`, model `LEAD_DESK_GEMINI_MODEL`, default `gemini-3.6-flash`) with a fixed ICP rubric, structured JSON output, and the same retry/backoff posture as the other two projects built tonight (3 attempts, exponential backoff, honors `Retry-After`, retries on 408/429/5xx only). The message is treated as untrusted data — the prompt explicitly tells the model never to follow instructions inside it.

Each signal (`company_size_signal`, `budget_signal`, `urgency_signal`, `intent`) requires a verbatim evidence quote from the message or is rejected as ungrounded, same evidence-grounding discipline as Project 2 and Track A. `score` is the model's own confidence in its classification, not a fixed formula — below `0.6` (`routing.CONFIDENCE_THRESHOLD`) it always routes to human review regardless of what classification was guessed, so an uncertain "cold" can never silently auto-dismiss a real lead, and an uncertain "hot" never wastes a rep's time on autopilot.

| Classification | Score | Route | Owner | CRM | Slack | Auto-reply |
|---|---|---|---|---|---|---|
| hot | ≥0.6 | `hot_assigned` | round-robin | yes | yes | no |
| warm | ≥0.6 | `warm_assigned` | round-robin | yes | yes | no |
| cold | ≥0.6 | `cold_auto_reply` | none | yes | **no** (no human needed) | **yes** |
| any/none | <0.6 or scorer failure | `needs_human_review` | none | yes | yes | no |

Owner assignment is a durable round-robin over `LEAD_DESK_OWNERS` (comma-separated) — the rotation index persists in SQLite across restarts. Zero owners configured forces even a hot lead to `needs_human_review` rather than silently dropping the assignment.

## CRM, Slack, and auto-reply — all dormant by default, all durable outboxes

Every finished lead gets exactly one row in each of three outbox kinds (CRM, Slack alert, auto-reply email), dry-run by default. Unlike an SMS to a customer, none of these three have a duplicate-send risk (an idempotent CRM upsert, a second Slack notice, a second polite email), so failures **retry automatically** up to 5 attempts before giving up — no frozen "needs review" state the way Track A's Twilio outbox intentionally has.

- **CRM (`lead_desk/crm.py`)**: HubSpot only for now, via `LEAD_DESK_CRM_MODE=hubspot` + `LEAD_DESK_HUBSPOT_TOKEN` (a free-tier Private App token — no paid HubSpot account needed to test this). Uses the batch upsert-by-email endpoint, so a retried write can never create a duplicate contact. Writes only standard properties guaranteed to exist on any portal (name/phone/company); attempts two custom properties (`lead_desk_score`, `lead_desk_classification`) and automatically drops them on the one retry if the portal doesn't have them configured, rather than failing the whole write over an optional field. **Not yet live-verified against a real HubSpot account** — needs a real Private App token to confirm the actual API contract, same as Track A's Twilio and Project 2's Gemini both needed a real credential before first live use.
- **Slack alert (`lead_desk/alerts.py`)**: `ALERT_MODE=webhook` + `ALERT_WEBHOOK_URL` — any Slack/Discord incoming webhook or custom endpoint. Live-verified tonight against a real HTTP endpoint through the actual async worker loop, not just a mocked unit test.
- **Auto-reply (`lead_desk/autoreply.py`)**: `LEAD_DESK_AUTOREPLY_MODE=resend` + `LEAD_DESK_RESEND_API_KEY` + `LEAD_DESK_FROM_EMAIL` (Resend, same provider already used for Eagle Solectra). Not yet live-verified.

## Weekly scorecard

`GET /scorecard?days=7` — leads in, qualified (hot+warm), needs-review count, breakdown by source and by classification, computed live from the SQLite store. No separate dashboard app; this is the "Google Sheet or CRM dashboard" requirement from the plan, as a JSON endpoint an operator can check or pipe into anything else.

## Reliability and verification

22 tests cover: round-robin assignment and its wraparound, the confidence threshold forcing review, scorer-failure handling, empty-message handling, the zero-owners fallback, idempotency (same-id, same-content, and the same-content-different-id dedup-to-canonical case), all three outbox kinds' dry-run/retry/give-up behavior including the route-based gating (no Slack for cold, no auto-reply for hot/warm), the HubSpot custom-property fallback, source normalization (generic passthrough + Typeform's nested shape), and the scorecard aggregation.

**One test specifically exercises the real asyncio worker loop the way `uvicorn` would run it** (`test_live_async_workers_actually_process_a_real_lead`), not just direct calls to `process_one`/`process_outbox` — this class of bug (wrong arguments passed into `asyncio.to_thread`, silently breaking every worker tick while every direct-call unit test keeps passing) was found and fixed live in Track A earlier the same night; this project was built with that lesson already applied, and confirmed live against a real webhook (httpbin.org) for both the extraction worker and the alert worker before this note was written.

Two real bugs were found and fixed during this build via live testing, not caught by any unit test:
1. The demo's scripted scorer did a case-sensitive substring match against message text that used different capitalization, silently misclassifying the "warm" demo story as "cold." Fixed, and the demo now asserts every story routes as expected (mirroring Track A's own demo assertion) so this can't silently regress.
2. The initial idempotency design raised a conflict when identical content arrived under a new auto-generated id, instead of deduplicating to the existing canonical record — caught before any test was written against it, by comparing directly against Project 2's already-proven SHA-256 dedup semantics.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## What is not built yet

- **Meta Lead Ads / Google Lead Form / Webflow / GHL native API integrations.** These are treated as "generic" sources per the plan's own equivalence ("a webhook" is listed as one of the acceptable sources) — connecting each platform's own webhook/Zapier export to `/webhooks/lead/generic` is a per-client setup step, not unbuilt code, the same way Track A's Twilio number is a setup step and not a receiver rewrite.
- **Real CRM/Slack/auto-reply verification against live accounts.** Slack is live-verified against a real endpoint; HubSpot and Resend are not yet — both need a real credential from Rajan, same pattern as Gemini/Twilio needed tonight.
- **GoHighLevel and Pipedrive CRM writers.** Plan allows any of HubSpot/GoHighLevel/Pipedrive; only HubSpot is built, since it has a genuinely free developer tier to test against without spending money.
- **Multi-source add-on pricing/upsell logic, the loom video, the credentials handover doc.** Those are delivery-process/business items from the plan, not code.
