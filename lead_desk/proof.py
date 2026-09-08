PROOF_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Lead Desk — Working Proof</title>
  <style>
    :root{--ink:#14213d;--blue:#102a43;--accent:#168aad;--paper:#f4f7fb;--line:#dce8f2}
    *{box-sizing:border-box}body{margin:0;background:var(--paper);font:16px/1.55 Arial,sans-serif;color:var(--ink)}
    main{max-width:1120px;margin:auto;padding:48px 24px}.hero{background:var(--blue);color:#fff;border-radius:24px;padding:38px 42px}
    h1{font-size:clamp(36px,6vw,56px);line-height:1.05;margin:10px 0 14px}h2{font-size:24px;margin:8px 0 12px}
    .hero p{max-width:760px;font-size:19px;color:#d8ebf8;margin:0}.badge{display:inline-block;background:#ffcf56;color:var(--ink);border-radius:999px;padding:7px 13px;font-size:12px;font-weight:700;letter-spacing:.04em}
    .proof{margin:22px 0 0;padding:16px 18px;background:#fff;border:1px solid var(--line);border-radius:14px}
    .grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;margin-top:22px}
    article{background:#fff;border:1px solid var(--line);border-radius:18px;padding:26px;box-shadow:0 8px 24px #102a430d}
    .num{color:var(--accent);font-weight:700;font-size:13px;letter-spacing:.08em}.example{background:#eef6fb;border-left:4px solid var(--accent);padding:14px 16px;border-radius:9px}
    .pill{display:inline-block;margin-top:12px;padding:7px 11px;border-radius:999px;background:#e4f1e9;color:#18794e;font-size:13px;font-weight:700}
    footer{margin-top:22px;padding:18px 20px;background:#e8f1fb;border-radius:14px;color:#36516b;font-size:14px}
    @media(max-width:760px){main{padding:24px 16px}.hero{padding:28px 24px}.grid{grid-template-columns:1fr}}
  </style>
</head>
<body>
<main>
  <section class="hero">
    <span class="badge">WORKING PROOF · FICTIONAL LEADS ONLY</span>
    <h1>Lead Desk</h1>
    <p>Inbound enquiries classified against an ICP, assigned by round-robin, written to HubSpot, and briefed to the team automatically. Uncertain leads are flagged for human review.</p>
  </section>
  <div class="proof"><strong>Verified scope:</strong> Gemini classification, HubSpot contact upsert, Slack/Discord webhook alert, Resend auto-reply, durable retries, duplicate protection, authenticated operational endpoints, and a weekly scorecard.</div>
  <section class="grid">
    <article><div class="num">01 · INBOUND</div><h2>A lead arrives</h2><div class="example">“We are a 15-person agency spending about $8k/month on Meta ads. We need a lead qualification system within two weeks.”</div><p>The existing form sends one normalized webhook payload.</p></article>
    <article><div class="num">02 · CLASSIFY</div><h2>Evidence-backed classification</h2><div class="example"><strong>HOT</strong><br>Budget named · timeline named · buying intent present</div><span class="pill">Confidence gated</span></article>
    <article><div class="num">03 · ASSIGN</div><h2>Round-robin ownership</h2><div class="example"><strong>Assigned owner:</strong> Owner A<br><strong>Route:</strong> hot_assigned<br><strong>CRM:</strong> HubSpot upsert queued</div><span class="pill">Durable assignment</span></article>
    <article><div class="num">04 · ALERT</div><h2>The team gets a short brief</h2><div class="example"><strong>HOT LEAD</strong><br>Hot Agency → Owner A<br>Named budget, timeline, and clear buying language.</div><span class="pill">Webhook alert</span></article>
    <article><div class="num">05 · SAFETY NET</div><h2>Uncertain leads are reviewed</h2><p>A low-confidence result goes to human review. A confidently poor-fit enquiry receives a polite automatic response.</p><span class="pill">No silent guess</span></article>
    <article><div class="num">06 · SCORECARD</div><h2>The week is measurable</h2><div class="example"><strong>Leads in</strong> · <strong>qualified</strong> · <strong>needs review</strong><br>Breakdown by source and classification</div><span class="pill">Live aggregation</span></article>
  </section>
  <footer>This is a self-initiated portfolio project. The workflow was verified against real service accounts using synthetic test data. It does not claim a client deployment, response-time result, conversion lift, or revenue outcome.</footer>
</main>
</body>
</html>"""
