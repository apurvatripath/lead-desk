const owners = ['Alice Nguyen', 'Bob Ferreira'];
let ownerIndex = 0;
function nextOwner() { const o = owners[ownerIndex % owners.length]; ownerIndex++; return o; }

function pickSeed(kind) {
  const pool = seedPool[kind];
  const i = seedCounters[kind] % pool.length;
  seedCounters[kind]++;
  return { ...pool[i], id: kind + Date.now() + '-' + i };
}

const CLASS_META = {
  hot: { icon: 'HOT', label: 'Hot lead', pill: 'ready', conf: 'high' },
  warm: { icon: 'WARM', label: 'Warm lead', pill: 'ready', conf: 'high' },
  cold: { icon: 'COLD', label: 'Cold lead', pill: 'warning', conf: 'high' },
  review: { icon: 'REV', label: 'Needs human review', pill: 'review', conf: 'low' }
};

function buildRecord(kind, seed) {
  const meta = CLASS_META[kind];
  const owner = (kind === 'hot' || kind === 'warm') ? nextOwner() : null;
  const rec = {
    id: seed.id, type: kind, name: seed.name, company: seed.company,
    rowMeta: seed.source + ' · just now', confidencePct: seed.confidence,
    kicker: meta.label, statusPill: meta.pill, confClass: meta.conf,
    fields: seed.fields,
    owner: owner,
    email: seed.email || ''
  };
  if (kind === 'hot' || kind === 'warm') {
    rec.orderState = 'ready'; rec.orderStateLabel = kind === 'hot' ? 'Assigned' : 'Assigned';
    rec.recommendationTitle = 'Assign a person and post Slack';
    rec.recommendation = `Would assign ${owner} and would write to HubSpot — not connected. Slack below is a dry-run mock.`;
    rec.message = `New ${kind} lead — ${seed.name} (${seed.company}). Score ${seed.confidence}%. ${seed.fields[3][1]} Assigned to ${owner}.`;
    rec.slack = rec.message;
    rec.replyKind = 'slack';
    rec.email = seed.email || '';
    rec.timeline = [
      ['Lead received', seed.source], [`Classified ${kind}`, `${seed.confidence}% confidence`], [`Routed to ${owner}`, 'Would write HubSpot · would Slack owner']
    ];
  } else if (kind === 'cold') {
    rec.orderState = 'ready'; rec.orderStateLabel = 'Auto-replied';
    rec.recommendationTitle = 'Auto-reply the cold lead';
    rec.recommendation = 'No owner ping. Would send the reply below. Would still log the contact to HubSpot — not connected.';
    rec.message = `Hi ${seed.name.split(' ')[0]}, thanks for reaching out. This isn't a fit right now — we've noted your message in case that changes.`;
    rec.slack = '';
    rec.replyKind = 'email';
    rec.email = seed.email || '';
    rec.timeline = [
      ['Lead received', seed.source], ['Classified cold', `${seed.confidence}% confidence`], ['Auto-reply queued', 'Would send · no owner ping']
    ];
  } else {
    rec.orderState = 'flagged'; rec.orderStateLabel = 'Needs review';
    rec.recommendationTitle = 'Flag for a human — do not guess';
    rec.recommendation = `Confidence ${seed.confidence}% is below 60%. Would not Slack or auto-reply. Would write an unclassified HubSpot record — not connected.`;
    rec.message = 'Held for a person. No Slack ping, no auto-reply.';
    rec.slack = rec.message;
    rec.replyKind = 'slack';
    rec.email = seed.email || '';
    rec.timeline = [
      ['Lead received', seed.source], ['Scorer uncertain', `${seed.confidence}% confidence · below threshold`], ['Flagged for review', 'Waiting on a person']
    ];
  }
  return rec;
}

const seedPool = {
  hot: [
    { name: 'Elena Vargas', company: 'Northline Media', email: 'elena@northlinemedia.co', source: 'Meta Lead Ads', confidence: 92,
      fields: [['Company', 'Northline Media · 15 people'], ['Quote from form', '"We spend about $8k/month on Meta. Need lead qualification live in two weeks."'], ['Budget / timeline', '$8k/mo ads · 2 weeks'], ['Intent', 'Buy a qualification workflow']] },
    { name: 'Marcus Chen', company: 'Brightside Digital', email: 'marcus@brightsidedigital.com', source: 'Google Ads form', confidence: 89,
      fields: [['Company', 'Brightside Digital · 11 people'], ['Quote from form', '"HubSpot is a mess after the form fills. Can you wire scoring and Slack?"'], ['Budget / timeline', 'Named project budget · this month'], ['Intent', 'Install inbound routing']] },
    { name: 'Hannah Cole', company: 'Pike & Rowan', email: 'hannah@pikeandrowan.com', source: 'Website contact', confidence: 94,
      fields: [['Company', 'Pike & Rowan · UK agency'], ['Quote from form', '"Paid leads sit overnight. We need hot/warm/cold and an owner on Slack."'], ['Budget / timeline', 'Retainer mentioned · start next sprint'], ['Intent', 'Replace manual triage']] }
  ],
  warm: [
    { name: 'Priya Shah', company: 'Harbor & Co', email: 'priya@harborandco.com', source: 'Website contact', confidence: 76,
      fields: [['Company', 'Harbor & Co · 8 people'], ['Quote from form', '"Can you send pricing for HubSpot cleanup this quarter?"'], ['Budget / timeline', 'This quarter · no number yet'], ['Intent', 'Exploring a cleanup project']] },
    { name: 'Daniel Okonkwo', company: 'Lumen Agency', email: 'daniel@lumen.agency', source: 'LinkedIn form', confidence: 71,
      fields: [['Company', 'Lumen Agency · 22 people'], ['Quote from form', '"We might need help routing inbound. Send a one-pager."'], ['Budget / timeline', 'Not named · this quarter'], ['Intent', 'Requesting a walkthrough']] }
  ],
  cold: [
    { name: 'Jordan Miles', company: '—', email: 'jordan.miles.dev@gmail.com', source: 'Website contact', confidence: 91,
      fields: [['Company size', 'Not a company'], ['Budget', 'Not mentioned'], ['Urgency', 'None'], ['Intent', '"Are you hiring developers?"']] },
    { name: 'Aisha Rahman', company: 'TalentBridge', email: 'aisha@talentbridge.example', source: 'Website contact', confidence: 88,
      fields: [['Company size', 'Recruiter / staffing'], ['Budget', 'Not a buyer'], ['Urgency', 'None'], ['Intent', '"I have Java roles in Bangalore — 15% fee"']] }
  ],
  review: [
    { name: 'Sam Whitaker', company: 'Unclear — no domain', email: 'samw114@gmail.com', source: 'Meta Lead Ads', confidence: 54,
      fields: [['Company size', 'Ambiguous — "we\'re growing"'], ['Budget', 'Not mentioned'], ['Urgency', 'Ambiguous'], ['Intent', '"Tell me more"']] },
    { name: 'Chris Patel', company: 'GrowthLab', email: 'hello@growthlab.io', source: 'Google Ads form', confidence: 51,
      fields: [['Company size', 'Not stated'], ['Budget', '"depends"'], ['Urgency', 'Not stated'], ['Intent', '"Do you also do SEO and ads?"']] }
  ]
};
let seedCounters = { hot: 0, warm: 0, cold: 0, review: 0 };

const records = {};
const order = [];
['hot', 'warm', 'cold', 'review'].forEach((kind) => {
  const seed = pickSeed(kind);
  records[seed.id] = buildRecord(kind, seed);
  order.push(seed.id);
});

let selected = order[0];
let activeFilter = 'all';
const activity = [
  { dot: 'green', title: 'Hot lead assigned', meta: 'Elena Vargas · Northline Media · Alice Nguyen' },
  { dot: 'green', title: 'Warm lead assigned', meta: 'Priya Shah · Harbor & Co · Bob Ferreira' },
  { dot: 'blue', title: 'Cold lead auto-replied', meta: 'Jordan Miles · job-seeker · no owner' },
  { dot: 'amber', title: 'Lead flagged for review', meta: 'Sam Whitaker · 54% · below 60% threshold' }
];

function counts() {
  const c = { all: order.length, hot: 0, warm: 0, cold: 0, review: 0 };
  order.forEach(id => c[records[id].type]++);
  return c;
}

function renderList() {
  const listEl = document.getElementById('orderList');
  const c = counts();
  document.getElementById('tabAll').textContent = c.all;
  document.getElementById('tabHot').textContent = c.hot;
  document.getElementById('tabWarm').textContent = c.warm;
  document.getElementById('tabCold').textContent = c.cold;
  document.getElementById('tabReview').textContent = c.review;
  document.getElementById('showingCount').textContent = activeFilter === 'all' ? c.all : c[activeFilter];
  document.getElementById('navLeads').textContent = c.all;
  document.getElementById('navReview').textContent = c.review;

  listEl.innerHTML = '';
  order.filter(id => activeFilter === 'all' || records[id].type === activeFilter).forEach(id => {
    const r = records[id];
    const meta = CLASS_META[r.type];
    const btn = document.createElement('button');
    btn.className = 'order-row' + (id === selected ? ' selected' : '');
    btn.dataset.id = id;
    btn.innerHTML = `<span class="source-icon ${r.type}">${meta.icon}</span><span class="order-main"><strong>${r.name} · ${r.company}</strong><small>${r.rowMeta}</small></span><span class="order-state ${r.orderState}">${r.orderStateLabel}</span><span class="confidence ${r.confClass}">${r.confidencePct}%</span><span class="chevron">›</span>`;
    btn.addEventListener('click', () => { selected = id; renderList(); renderDetail(); });
    listEl.appendChild(btn);
  });
}

function renderDetail() {
  const r = records[selected];
  const meta = CLASS_META[r.type];
  document.getElementById('detailIcon').className = 'source-icon ' + r.type;
  document.getElementById('detailIcon').textContent = meta.icon;
  document.getElementById('detailKicker').textContent = meta.label;
  document.getElementById('detailTitle').textContent = `${r.name} · ${r.company}`;
  document.getElementById('detailStatus').className = 'status-pill ' + r.statusPill;
  document.getElementById('detailStatus').textContent = r.orderStateLabel;
  document.getElementById('detailMeta').textContent = r.rowMeta.replace(' · just now', ' · received just now');
  document.getElementById('detailConfidence').textContent = r.confidencePct + '% confidence';
  document.getElementById('fieldGrid').innerHTML = r.fields.map(([label, val]) =>
    `<div class="field"><label>${label}</label><strong>${val}</strong></div>`).join('');
  document.getElementById('recommendationTitle').textContent = r.recommendationTitle;
  document.getElementById('recommendation').textContent = r.recommendation;
  const slack = document.getElementById('slackMock');
  const thread = document.getElementById('replyThread');
  if (r.replyKind === 'email') {
    slack.hidden = true;
    thread.hidden = false;
    thread.innerHTML = `<div class="bubble out">${r.message}</div><div class="bubble sys">Auto-reply · dry-run · not sent</div>`;
  } else {
    thread.hidden = true;
    slack.hidden = false;
    document.getElementById('slackBody').textContent = r.slack || r.message;
  }
  document.getElementById('hsBody').textContent = `${r.name} · ${r.company}\nEmail: ${r.email || 'not provided'}\nLifecycle: lead\nOwner: ${r.owner || 'unassigned'}\nNote: ${r.fields[1][1]}`;
  document.getElementById('timeline1Title').textContent = r.timeline[0][0];
  document.getElementById('timeline1Meta').textContent = r.timeline[0][1];
  document.getElementById('timeline2Title').textContent = r.timeline[1][0];
  document.getElementById('timeline2Meta').textContent = r.timeline[1][1];
  document.getElementById('timeline3Title').textContent = r.timeline[2][0];
  document.getElementById('timeline3Meta').textContent = r.timeline[2][1];
}

function renderActivity() {
  document.getElementById('activityList').innerHTML = activity.slice(0, 6).map(a =>
    `<div><span class="activity-dot ${a.dot}"></span><p><strong>${a.title}</strong><small>${a.meta}</small></p></div>`).join('');
}

function showToast(text) {
  const t = document.getElementById('toast');
  t.textContent = text;
  t.classList.add('show');
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => t.classList.remove('show'), 3200);
}

function bumpMetric(id, delta) {
  const el = document.getElementById(id);
  el.textContent = parseInt(el.textContent, 10) + delta;
}

function simulate(kind) {
  const seed = pickSeed(kind);
  const rec = buildRecord(kind, seed);
  records[seed.id] = rec;
  order.unshift(seed.id);
  selected = seed.id;
  activeFilter = 'all';
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.filter === 'all'));
  renderList();
  renderDetail();
  const row = document.querySelector('.order-row.selected');
  if (row) {
    row.classList.add('row-flash');
    row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  document.getElementById('activityList').classList.add('ping');
  setTimeout(() => document.getElementById('activityList').classList.remove('ping'), 1100);
  bumpMetric('leadsMetric', 1);
  if (kind === 'review') {
    bumpMetric('reviewMetric', 1);
    showToast(`Lead flagged for review — ${rec.confidencePct}% confidence, below threshold.`);
    activity.unshift({ dot: 'amber', title: 'Lead flagged for review', meta: `${seed.name} · ${rec.confidencePct}% confidence` });
  } else {
    bumpMetric('routedMetric', 1);
    if (kind === 'cold') {
      showToast(`Cold lead auto-replied — no owner needed.`);
      activity.unshift({ dot: 'blue', title: 'Cold lead auto-replied', meta: `${seed.name} · no owner assigned` });
    } else {
      showToast(`${kind === 'hot' ? 'Hot' : 'Warm'} lead would Slack ${rec.owner}. Would write to HubSpot — not connected.`);
      activity.unshift({ dot: 'green', title: `${kind === 'hot' ? 'Hot' : 'Warm'} lead assigned`, meta: `${seed.name} · ${seed.company} · routed to ${rec.owner}` });
    }
  }
  renderActivity();
}

document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    activeFilter = tab.dataset.filter;
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t === tab));
    renderList();
  });
});

document.getElementById('simHotBtn').addEventListener('click', () => simulate('hot'));
document.getElementById('simWarmBtn').addEventListener('click', () => simulate('warm'));
document.getElementById('simColdBtn').addEventListener('click', () => simulate('cold'));
document.getElementById('simReviewBtn').addEventListener('click', () => simulate('review'));
document.getElementById('reviewBtn').addEventListener('click', () => showToast('Flagged for review — a person will confirm the classification.'));
document.getElementById('moreBtn').addEventListener('click', () => {
  const menu = document.getElementById('moreMenu');
  menu.hidden = !menu.hidden;
});
document.addEventListener('click', (e) => {
  if (!e.target.closest('.sim-wrap')) document.getElementById('moreMenu').hidden = true;
});
document.getElementById('actionBtn').addEventListener('click', () => {
  document.getElementById('hsModal').classList.add('show');
});
document.getElementById('hsClose').addEventListener('click', () => document.getElementById('hsModal').classList.remove('show'));
document.getElementById('hsModal').addEventListener('click', (e) => {
  if (e.target.id === 'hsModal') e.target.classList.remove('show');
});

renderList();
renderDetail();
renderActivity();
