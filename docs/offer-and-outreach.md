# Lead Desk — offer + outreach sequence

Matches the operating plan's Days 1-14 collateral requirement (1-page offer PDF, 3-touch email sequence). Real proof points only — nothing here claims a client that doesn't exist.

## 1-page offer

**Promise** (use verbatim in every email and call):
> Inbound leads scored, routed, and briefed to the right person in under two minutes — or they never touch a human.

**Scope (fixed, v1):**
- One inbound source: Meta Lead Ads, Google Lead Form, Typeform, Webflow, GHL form, or a webhook.
- AI extraction of name, company, role, intent, budget signals, notes.
- Scoring rubric written with the client (their ICP, not a generic model).
- Write to HubSpot, GoHighLevel, or Pipedrive. Assign owner by round-robin or territory.
- Slack/email alert with score, 3-line brief, CRM link.
- Low-score leads: polite auto-reply + tag, no human touch.
- Weekly scorecard: leads in / qualified / missed SLA / by source.

**What's out of scope in v1:** rebuilding their site/ads/funnel, multi-source omnichannel, calling the lead (voice is a later upsell), anything needing a lawyer/CA license/HIPAA/SOC2 on day one.

**Price:** $4,500 implementation (2-week install) + $1,500/month retain. First 3 logos: $2,500 + $1,000/month in exchange for a named case study.

**Timeline:** 2-week install from kickoff. Handover: loom walkthrough + credentials doc + 14-day warranty on the v1 flow.

**What we need from them:** access to their lead source (form/ad account/webhook), a CRM login (HubSpot/GHL/Pipedrive), 45 minutes to define their actual scoring rubric, and who the leads route to.

**Real proof, not a mockup:** live at `https://lead-desk-production-d4dd.up.railway.app` — Gemini scoring, HubSpot write (contact `547946992365`, read back from HubSpot's own API), Discord owner alert (message `1546506274190139402`), Resend auto-reply, all verified against real accounts, not sandboxed.

## 3-touch email sequence (Day 0 / Day 3 / Day 10)

**Touch 1 — Day 0** (90 words max, no attachment, no "AI-powered"):

> Subject: speed to lead at {Agency}
>
> {Name} — noticed {Agency} runs paid leads into {HubSpot/GoHighLevel}. Most teams at your size are still 30+ hours from form-fill to first human touch, even with good ads.
>
> I built a fixed-scope install that scores and routes an inbound lead to the right person in under two minutes — dead leads get an auto-reply instead of silence. Live, not a mockup: [link].
>
> Worth 12 minutes to see it against your actual stack?
>
> {Your name}

**Touch 2 — Day 3** (forward of the same thread, two lines):

> Most teams we talk to are at 30+ hours first-touch. The walkthrough is 4 minutes if useful — happy to run it against {Agency}'s actual form instead of the generic demo.

**Touch 3 — Day 10** (breakup):

> Closing the loop on this. If inbound qualification at {Agency} is already instant, ignore this. If not, the offer is a 2-week fixed-price install — no retainer commitment until you've seen it work on your own leads.

**Rules:** send from a warmed domain, not a personal Gmail. 40-50 new contacts/day after warmup, not a blast on day one. Book calls on a public Calendly, two slots per weekday (evening IST / morning US).

## Target list criteria (for the 150-account build)

- **Country:** United States, United Kingdom, Australia.
- **Employees:** 5-30.
- **Industry:** Marketing & Advertising, or Staffing & Recruiting.
- **Title:** Owner, Founder, CEO, Managing Partner, Head of Operations, Agency Partner.
- **Tech signal:** HubSpot or GoHighLevel/"HighLevel" visible (website footer, job posts, case studies).
- **Exclude:** holding companies, 100+ FTE, Indian agencies pitching the same service (not a target, a competitor).

## Still open

- **The loom** — 4-minute walkthrough on the live Railway app, same recurring gap as Project 2's. Needs Rajan's narration; script can reuse the same "show the flow, name the leak, name the safety net" shape as Project 2's.
- **Domain + Google Workspace + email warmup** — nothing here has a dedicated send domain yet; sending from a personal Gmail burns the account per the plan's own rule.
