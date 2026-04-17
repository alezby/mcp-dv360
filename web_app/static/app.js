/* YouTube Brand Lift Auditor — frontend logic */

const VERTICALS = ["DEFAULT","CPG","AUTO","TECH","RETAIL","FINANCE","ENTERTAINMENT","HEALTHCARE","TRAVEL"];
const OBJECTIVES = ["AWARENESS","CONSIDERATION","ACTION"];
const FORMATS = ["SKIPPABLE_IN_STREAM","BUMPER","IN_FEED","OUTSTREAM"];

let state = {
  advertisers: [],
  campaigns: [],
  creatives: [],
  lineItems: [],
  auditResult: null,
};

// ─── Init ──────────────────────────────────────────────────────────────────

async function init() {
  const { authenticated, email } = await api("/auth/status");
  if (authenticated) {
    showScreen("audit");
    document.getElementById("user-email").textContent = email || "Connected";
    document.getElementById("header-user").classList.remove("hidden");
    await loadAdvertisers();
  } else {
    showScreen("auth");
    document.getElementById("header-user").classList.add("hidden");
  }
}

// ─── Screen routing ────────────────────────────────────────────────────────

function showScreen(name) {
  document.querySelectorAll("section[id$='-screen']").forEach(s => s.classList.remove("active"));
  document.getElementById(`${name}-screen`).classList.add("active");
  if (name === "audit") setStep(1);
}

function setStep(n) {
  document.querySelectorAll(".step").forEach((el, i) => {
    el.classList.toggle("active", i + 1 === n);
    el.classList.toggle("done", i + 1 < n);
  });
  document.querySelectorAll(".step-panel").forEach((el, i) => {
    el.classList.toggle("hidden", i + 1 !== n);
  });
}

// ─── API helpers ───────────────────────────────────────────────────────────

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json();
}

function showError(msg) {
  const el = document.getElementById("error-banner");
  el.textContent = msg;
  el.style.display = "block";
  setTimeout(() => { el.style.display = "none"; }, 8000);
}

// ─── Step 1: Advertiser ────────────────────────────────────────────────────

async function loadAdvertisers() {
  const sel = document.getElementById("sel-advertiser");
  sel.innerHTML = '<option value="">Loading…</option>';
  sel.disabled = true;
  try {
    state.advertisers = await api("/api/advertisers");
    sel.innerHTML = '<option value="">— Select advertiser —</option>';
    state.advertisers.forEach(a => {
      const o = document.createElement("option");
      o.value = a.id;
      o.textContent = `${a.name} (${a.id})`;
      sel.appendChild(o);
    });
    sel.disabled = false;
  } catch (e) {
    sel.innerHTML = '<option value="">Failed to load — enter ID manually</option>';
    document.getElementById("manual-advertiser-row").classList.remove("hidden");
    sel.disabled = false;
    showError("Could not load advertisers: " + e.message);
  }
}

document.getElementById("sel-advertiser").addEventListener("change", async function () {
  const aid = this.value;
  if (!aid) return;
  await Promise.all([loadCampaigns(aid), loadCreatives(aid), loadLineItems(aid)]);
});

async function loadCampaigns(aid) {
  const sel = document.getElementById("sel-campaign");
  sel.innerHTML = '<option value="">Loading…</option>';
  try {
    state.campaigns = await api(`/api/campaigns/${aid}`);
    sel.innerHTML = '<option value="">(optional)</option>';
    state.campaigns.forEach(c => {
      const o = document.createElement("option");
      o.value = c.id;
      o.textContent = `${c.name} (${c.id})`;
      sel.appendChild(o);
    });
  } catch (e) {
    sel.innerHTML = '<option value="">(optional)</option>';
  }
}

async function loadCreatives(aid) {
  const sel = document.getElementById("sel-creative");
  sel.innerHTML = '<option value="">Loading…</option>';
  try {
    state.creatives = await api(`/api/creatives/${aid}`);
    sel.innerHTML = '<option value="">(optional)</option>';
    state.creatives.forEach(c => {
      const o = document.createElement("option");
      o.value = c.id;
      o.textContent = `${c.name} — ${c.type} ${c.duration ? "(" + c.duration + ")" : ""} (${c.id})`;
      sel.appendChild(o);
    });
  } catch (e) {
    sel.innerHTML = '<option value="">(optional)</option>';
  }
}

async function loadLineItems(aid, cid = null) {
  const sel = document.getElementById("sel-line-item");
  sel.innerHTML = '<option value="">Loading…</option>';
  try {
    const qs = cid ? `?campaign_id=${cid}` : "";
    state.lineItems = await api(`/api/line-items/${aid}${qs}`);
    sel.innerHTML = '<option value="">(optional)</option>';
    state.lineItems.forEach(li => {
      const o = document.createElement("option");
      o.value = li.id;
      o.textContent = `${li.name} (${li.id})`;
      sel.appendChild(o);
    });
  } catch (e) {
    sel.innerHTML = '<option value="">(optional)</option>';
  }
}

document.getElementById("sel-campaign").addEventListener("change", function () {
  const aid = document.getElementById("sel-advertiser").value;
  if (aid && this.value) loadLineItems(aid, this.value);
});

function goToStep2() {
  const aid = document.getElementById("sel-advertiser").value
    || document.getElementById("input-advertiser-manual").value.trim();
  if (!aid) { showError("Please select or enter an advertiser ID."); return; }
  setStep(2);
}

// ─── Step 2: Creative / Line item ─────────────────────────────────────────

function goToStep3() { setStep(3); }
function backToStep1() { setStep(1); }

// Toggle manual duration+format when no creative selected
document.getElementById("sel-creative").addEventListener("change", function () {
  const manualRow = document.getElementById("manual-creative-row");
  manualRow.classList.toggle("hidden", !!this.value);
});

// ─── Step 3: Parameters ────────────────────────────────────────────────────

function backToStep2() { setStep(2); }

// Populate dropdowns
(function populateDropdowns() {
  const vSel = document.getElementById("sel-vertical");
  VERTICALS.forEach(v => {
    const o = document.createElement("option");
    o.value = v;
    o.textContent = v;
    vSel.appendChild(o);
  });

  const objSel = document.getElementById("sel-objective");
  OBJECTIVES.forEach(v => {
    const o = document.createElement("option");
    o.value = v;
    o.textContent = v;
    objSel.appendChild(o);
  });

  const fmtSel = document.getElementById("sel-format");
  fmtSel.innerHTML = '<option value="">(auto-detect or none)</option>';
  FORMATS.forEach(v => {
    const o = document.createElement("option");
    o.value = v;
    o.textContent = v.replace(/_/g, " ");
    fmtSel.appendChild(o);
  });
})();

// ─── Run audit ─────────────────────────────────────────────────────────────

async function runAudit() {
  const aid = document.getElementById("sel-advertiser").value
    || document.getElementById("input-advertiser-manual").value.trim();

  if (!aid) { showError("Advertiser ID is required."); return; }

  const body = {
    advertiser_id: aid,
    creative_id: document.getElementById("sel-creative").value || null,
    line_item_id: document.getElementById("sel-line-item").value || null,
    campaign_id: document.getElementById("sel-campaign").value || null,
    industry_vertical: document.getElementById("sel-vertical").value || "DEFAULT",
    campaign_objective: document.getElementById("sel-objective").value || "AWARENESS",
    video_duration_seconds: parseInt(document.getElementById("input-duration").value) || null,
    video_format: document.getElementById("sel-format").value || null,
    target_frequency: parseFloat(document.getElementById("input-frequency").value) || null,
    budget_usd: parseFloat(document.getElementById("input-budget").value) || null,
  };

  showScreen("loading");

  try {
    state.auditResult = await api("/api/audit", {
      method: "POST",
      body: JSON.stringify(body),
    });
    renderResults(state.auditResult);
    showScreen("results");
  } catch (e) {
    showScreen("audit");
    setStep(3);
    showError("Audit failed: " + e.message);
  }
}

// ─── Render results ────────────────────────────────────────────────────────

function renderResults(r) {
  const s = r.audit_summary;
  const c = r.creative_assessment;
  const t = r.targeting_assessment;
  const l = r.predicted_brand_lift;
  const b = r.industry_benchmarks;

  // Gauge
  renderGauge(s.overall_score);

  // Lift potential
  const lp = document.getElementById("lift-potential");
  lp.textContent = s.lift_potential.replace(/_/g, " ");
  lp.className = `lift-potential lp-${s.lift_potential}`;

  // Recommendation badge
  const rb = document.getElementById("rec-badge");
  rb.textContent = s.recommendation.replace(/_/g, " ");
  rb.className = `recommendation-badge rec-${s.recommendation}`;

  // Context pills
  document.getElementById("ctx-vertical").textContent = s.industry_vertical;
  document.getElementById("ctx-objective").textContent = s.campaign_objective;

  // Sub-scores
  document.getElementById("creative-score-chip").innerHTML =
    `Creative <strong>${c.score}/100</strong>`;
  document.getElementById("targeting-score-chip").innerHTML =
    `Targeting <strong>${t.score}/100</strong>`;

  // Lift cards
  renderLiftCard("awareness", l.brand_awareness_lift_pct, "Brand Awareness", "👁");
  renderLiftCard("recall", l.ad_recall_lift_pct, "Ad Recall", "🧠");
  renderLiftCard("consideration", l.brand_consideration_lift_pct, "Consideration", "💭");
  renderLiftCard("intent", l.purchase_intent_lift_pct, "Purchase Intent", "🛒");

  // Confidence
  const confEl = document.getElementById("lift-confidence");
  confEl.textContent = l.confidence;
  confEl.className = `confidence conf-${l.confidence}`;

  // Benchmarks
  document.getElementById("bench-awareness").textContent = b.awareness_lift_range;
  document.getElementById("bench-recall").textContent = b.ad_recall_lift_range;
  document.getElementById("bench-consideration").textContent = b.consideration_lift_range;

  // Creative assessment
  renderAssessment("creative", c);

  // Targeting assessment
  renderAssessment("targeting", t);

  // Risk flags
  renderFlags(r.risk_flags || []);

  // Recommendations
  renderRecommendations(r.recommendations || []);
}

function renderGauge(score) {
  const r = 54, cx = 100, cy = 100;
  const circumference = Math.PI * r; // semicircle
  const filled = (score / 100) * circumference;

  const color = score >= 80 ? "#137333"
    : score >= 65 ? "#0d652d"
    : score >= 50 ? "#e37400"
    : "#c5221f";

  document.getElementById("gauge-svg").innerHTML = `
    <svg viewBox="0 0 200 110" width="180" height="99">
      <path d="M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}"
            fill="none" stroke="#e8eaed" stroke-width="14" stroke-linecap="round"/>
      <path d="M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}"
            fill="none" stroke="${color}" stroke-width="14" stroke-linecap="round"
            stroke-dasharray="${filled} ${circumference}"
            stroke-dashoffset="0"/>
      <text x="${cx}" y="${cy - 6}" text-anchor="middle"
            font-size="32" font-weight="700" fill="${color}">${score}</text>
      <text x="${cx}" y="${cy + 12}" text-anchor="middle"
            font-size="11" fill="#9aa0a6">out of 100</text>
    </svg>`;
}

function renderLiftCard(id, pct, label, icon) {
  const el = document.getElementById(`lift-${id}`);
  el.innerHTML = `
    <div class="lift-icon">${icon}</div>
    <div class="lift-label">${label}</div>
    <div class="lift-mid">${pct.mid}<span class="lift-unit">%</span></div>
    <div class="lift-range">${pct.low}% – ${pct.high}%</div>`;
}

function renderAssessment(type, data) {
  const card = document.getElementById(`${type}-assessment`);
  const score = data.score;
  const ringClass = score >= 80 ? "ring-green" : score >= 65 ? "ring-lime" : score >= 50 ? "ring-yellow" : "ring-red";

  let extra = "";
  if (type === "creative") {
    const fmt = (data.format || "").replace(/_/g, " ");
    const dur = data.duration_seconds ? `${data.duration_seconds}s` : "—";
    extra = `
      <div style="font-size:12px;color:#5f6368;margin-bottom:8px;">
        <strong>Format:</strong> ${fmt || "Unknown"} &nbsp;·&nbsp;
        <strong>Duration:</strong> ${dur} &nbsp;·&nbsp;
        <strong>Category:</strong> ${data.duration_category || "—"}<br>
        <strong>Alignment:</strong> ${data.objective_format_alignment || "—"}
      </div>`;
  } else {
    const types = (data.detected_targeting_types || []);
    extra = types.length
      ? `<div class="tag-list">${types.map(t => `<span class="tag">${t.replace(/_/g, " ")}</span>`).join("")}</div>`
      : `<p style="font-size:12px;color:#9aa0a6;margin-bottom:8px;">No audience targeting detected</p>`;
    extra += `<p style="font-size:12px;color:#5f6368;margin-top:6px;"><strong>Reach:</strong> ${data.reach_estimate || "—"}</p>`;
  }

  const strengths = (data.strengths || []).map(s => `<li>${s}</li>`).join("");
  const improvements = (data.improvements || []).map(s => `<li>${s}</li>`).join("");

  card.innerHTML = `
    <div class="assessment-header">
      <h3 style="margin:0">${type === "creative" ? "🎬 Creative" : "🎯 Targeting"}</h3>
      <div class="score-ring ${ringClass}">${score}</div>
    </div>
    ${extra}
    ${strengths ? `<ul class="bullet-list strengths" style="margin-top:10px">${strengths}</ul>` : ""}
    ${improvements ? `<ul class="bullet-list improvements" style="margin-top:6px">${improvements}</ul>` : ""}`;
}

function renderFlags(flags) {
  const wrap = document.getElementById("flags-wrap");
  const card = document.getElementById("flags-card");

  if (!flags.length) {
    card.classList.add("hidden");
    return;
  }

  card.classList.remove("hidden");
  wrap.innerHTML = flags.map(f => `
    <div class="flag flag-${f.severity}">
      <div>
        <span class="flag-badge">${f.severity}</span>
        <div class="flag-cat">${f.category.replace(/_/g, " ")}</div>
      </div>
      <div class="flag-text">${f.message}</div>
    </div>`).join("");
}

function renderRecommendations(recs) {
  const el = document.getElementById("rec-list");
  el.innerHTML = recs.length
    ? recs.map(r => `<li>${r}</li>`).join("")
    : `<li>No specific recommendations.</li>`;
}

// ─── New audit ─────────────────────────────────────────────────────────────

function newAudit() {
  showScreen("audit");
  setStep(1);
}

// ─── Bootstrap ─────────────────────────────────────────────────────────────

init();
