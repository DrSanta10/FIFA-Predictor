// World Cup 2026 Predictor -- frontend logic.
// Vanilla JS by design: this is a small, single-purpose dashboard, not
// an app that needs a framework's overhead.

const TEAM_FLAGS = {
  "Mexico": "\u{1F1F2}\u{1F1FD}", "South Africa": "\u{1F1FF}\u{1F1E6}",
  "South Korea": "\u{1F1F0}\u{1F1F7}", "Czech Republic": "\u{1F1E8}\u{1F1FF}",
  "Canada": "\u{1F1E8}\u{1F1E6}", "Bosnia and Herzegovina": "\u{1F1E7}\u{1F1E6}",
  "Qatar": "\u{1F1F6}\u{1F1E6}", "Switzerland": "\u{1F1E8}\u{1F1ED}",
  "Brazil": "\u{1F1E7}\u{1F1F7}", "Morocco": "\u{1F1F2}\u{1F1E6}",
  "Haiti": "\u{1F1ED}\u{1F1F9}", "United States": "\u{1F1FA}\u{1F1F8}",
  "Paraguay": "\u{1F1F5}\u{1F1FE}", "Australia": "\u{1F1E6}\u{1F1FA}",
  "Turkey": "\u{1F1F9}\u{1F1F7}", "Germany": "\u{1F1E9}\u{1F1EA}",
  "Cura\u00e7ao": "\u{1F1E8}\u{1F1FC}", "Ivory Coast": "\u{1F1E8}\u{1F1EE}",
  "Ecuador": "\u{1F1EA}\u{1F1E8}", "Netherlands": "\u{1F1F3}\u{1F1F1}",
  "Japan": "\u{1F1EF}\u{1F1F5}", "Sweden": "\u{1F1F8}\u{1F1EA}",
  "Tunisia": "\u{1F1F9}\u{1F1F3}", "Belgium": "\u{1F1E7}\u{1F1EA}",
  "New Zealand": "\u{1F1F3}\u{1F1FF}", "Egypt": "\u{1F1EA}\u{1F1EC}",
  "Iran": "\u{1F1EE}\u{1F1F7}", "Spain": "\u{1F1EA}\u{1F1F8}",
  "Cape Verde": "\u{1F1E8}\u{1F1FB}", "Saudi Arabia": "\u{1F1F8}\u{1F1E6}",
  "Uruguay": "\u{1F1FA}\u{1F1FE}", "France": "\u{1F1EB}\u{1F1F7}",
  "Norway": "\u{1F1F3}\u{1F1F4}", "Senegal": "\u{1F1F8}\u{1F1F3}",
  "Iraq": "\u{1F1EE}\u{1F1F6}", "Argentina": "\u{1F1E6}\u{1F1F7}",
  "Algeria": "\u{1F1E9}\u{1F1FF}", "Austria": "\u{1F1E6}\u{1F1F9}",
  "Jordan": "\u{1F1EF}\u{1F1F4}", "Portugal": "\u{1F1F5}\u{1F1F9}",
  "Uzbekistan": "\u{1F1FA}\u{1F1FF}", "Colombia": "\u{1F1E8}\u{1F1F4}",
  "DR Congo": "\u{1F1E8}\u{1F1E9}", "Croatia": "\u{1F1ED}\u{1F1F7}",
  "Ghana": "\u{1F1EC}\u{1F1ED}", "Panama": "\u{1F1F5}\u{1F1E6}",
  "England": "\u{1F3F4}\u{E0067}\u{E0062}\u{E0065}\u{E006E}\u{E0067}\u{E007F}",
  "Scotland": "\u{1F3F4}\u{E0067}\u{E0062}\u{E0073}\u{E0063}\u{E0074}\u{E007F}",
};

function flag(team) { return TEAM_FLAGS[team] || "\u26BD"; }
function pct(x) { return `${Math.round(x * 100)}%`; }

let latestSnapshot = null;
let predictionFilter = "all";

// ---------- Fetching ----------

async function loadSnapshot() {
  const res = await fetch("/api/snapshot");
  if (res.status === 409) {
    const body = await res.json();
    showEmptyState(body.message);
    return null;
  }
  if (!res.ok) throw new Error(`Snapshot request failed: ${res.status}`);
  return res.json();
}

function showEmptyState(message) {
  document.getElementById("hero").innerHTML = `<div class="hero-empty">${message}</div>`;
  document.getElementById("stage-badge").textContent = "No data";
}

async function refreshAll() {
  try {
    latestSnapshot = await loadSnapshot();
    if (latestSnapshot) renderAll(latestSnapshot);
  } catch (err) {
    showToast(err.message || "Couldn't load data", "error");
  }
}

// ---------- Rendering ----------

function renderAll(snap) {
  renderHeader(snap.meta);
  renderHero(snap.title_odds);
  renderRankings(snap.rankings);
  renderTitleOdds(snap.title_odds);
  renderStandings(snap.standings);
  renderPredictions(snap.predictions);
  renderBracket(snap.title_odds);
  renderAccuracy(snap.accuracy);
  renderAddResultTeams(snap.predictions);

  const footer = document.getElementById("last-loaded");
  if (snap.meta.loaded_at) {
    const d = new Date(snap.meta.loaded_at);
    footer.textContent = `Model state computed ${d.toLocaleString()}`;
  }
}

function renderHeader(meta) {
  document.getElementById("stage-badge").textContent = meta.stage;
  document.getElementById("stage-badge").classList.remove("badge--loading");
  document.getElementById("match-counts").textContent =
    `${meta.played} played \u00b7 ${meta.remaining} remaining`;
}

function renderHero(titleOdds) {
  const el = document.getElementById("hero");
  if (!titleOdds || titleOdds.length === 0) {
    el.innerHTML = `<div class="hero-empty">Knockout bracket odds aren't available yet -- check back once the bracket is set.</div>`;
    return;
  }
  const top = titleOdds[0];
  const runners = titleOdds.slice(1, 4);

  el.innerHTML = `
    <div class="hero-content">
      <div class="hero-label">Most likely champion</div>
      <div class="hero-main">
        <span class="hero-flag">${flag(top.team)}</span>
        <span class="hero-team">${top.team}</span>
        <span class="hero-pct">${pct(top.p_win_title)}</span>
      </div>
      <div class="hero-bar-track"><div class="hero-bar-fill" style="width:${(top.p_win_title * 100).toFixed(1)}%"></div></div>
      <div class="hero-runners">
        ${runners.map(r => `
          <div class="hero-runner">
            <span class="flag">${flag(r.team)}</span>
            <span>${r.team}</span>
            <span class="pct">${pct(r.p_win_title)}</span>
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

function renderRankings(rankings) {
  const tbody = document.querySelector("#rankings-table tbody");
  tbody.innerHTML = rankings.slice(0, 12).map(r => `
    <tr>
      <td class="rank">${r.rank}</td>
      <td>${flag(r.team)} ${r.team}</td>
      <td class="num">${r.elo}</td>
    </tr>
  `).join("");
}

function renderTitleOdds(titleOdds) {
  const el = document.getElementById("title-odds-list");
  if (!titleOdds || titleOdds.length === 0) {
    el.innerHTML = `<p class="muted">Not available yet.</p>`;
    return;
  }
  const max = Math.max(...titleOdds.map(t => t.p_win_title)) || 1;
  el.innerHTML = titleOdds.slice(0, 12).map(t => `
    <div class="bar-row">
      <span class="flag">${flag(t.team)}</span>
      <span class="name">${t.team}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${(t.p_win_title / max * 100).toFixed(1)}%"></span></span>
      <span class="bar-pct">${pct(t.p_win_title)}</span>
    </div>
  `).join("");
}

function renderStandings(standings) {
  const groups = {};
  standings.forEach(row => {
    groups[row.group] = groups[row.group] || [];
    groups[row.group].push(row);
  });

  const grid = document.getElementById("standings-grid");
  grid.innerHTML = Object.keys(groups).sort().map(letter => {
    const rows = groups[letter].sort((a, b) => a.position - b.position);
    return `
      <div class="group-card">
        <h3>Group ${letter}</h3>
        ${rows.map(r => `
          <div class="group-row ${r.position <= 2 ? "qualified" : ""}">
            <span class="pos">${r.position}</span>
            <span>${flag(r.team)} ${r.team}</span>
            <span class="num">${r.played}</span>
            <span class="num">${r.gd > 0 ? "+" : ""}${r.gd}</span>
            <span class="pts">${r.points}</span>
          </div>
        `).join("")}
      </div>
    `;
  }).join("");
}

function renderPredictions(predictions) {
  const filtered = predictions.filter(p => {
    if (predictionFilter === "group") return !p.is_knockout;
    if (predictionFilter === "knockout") return p.is_knockout;
    return true;
  });

  const el = document.getElementById("predictions-list");
  if (filtered.length === 0) {
    el.innerHTML = `<p class="muted">No matches in this view.</p>`;
    return;
  }

  el.innerHTML = filtered.map(p => `
    <div class="match-card">
      <div class="match-date">${formatDate(p.date)}</div>
      <div class="match-teams">
        <span class="match-team">${flag(p.home_team)} ${p.home_team}</span>
        <span class="match-vs">vs</span>
        <span class="match-team">${flag(p.away_team)} ${p.away_team}</span>
        <span class="match-probs">
          <span class="prob-seg"><span class="label">H</span><span class="value">${pct(p.home_win_prob)}</span></span>
          <span class="prob-seg"><span class="label">D</span><span class="value">${pct(p.draw_prob)}</span></span>
          <span class="prob-seg"><span class="label">A</span><span class="value">${pct(p.away_win_prob)}</span></span>
        </span>
      </div>
      <div class="match-meta">
        <span class="predicted-pill">${p.predicted_winner}</span>
        <span class="stage-pill">${p.is_knockout ? "Knockout" : "Group stage"}</span>
      </div>
    </div>
  `).join("");
}

function renderBracket(titleOdds) {
  const thead = document.querySelector("#bracket-table thead");
  const tbody = document.querySelector("#bracket-table tbody");
  if (!titleOdds || titleOdds.length === 0) {
    thead.innerHTML = "";
    tbody.innerHTML = `<tr><td class="muted">Bracket odds aren't available yet.</td></tr>`;
    return;
  }
  thead.innerHTML = `
    <tr>
      <th>Team</th><th class="num">Rd of 16</th><th class="num">Quarters</th>
      <th class="num">Semis</th><th class="num">Final</th><th class="num">3rd place</th>
      <th class="num">Title</th>
    </tr>
  `;
  tbody.innerHTML = titleOdds.map(t => `
    <tr>
      <td>${flag(t.team)} ${t.team}</td>
      <td class="num">${pct(t.p_reach_r16)}</td>
      <td class="num">${pct(t.p_reach_qf)}</td>
      <td class="num">${pct(t.p_reach_sf)}</td>
      <td class="num">${pct(t.p_reach_final)}</td>
      <td class="num">${pct(t.p_third_place)}</td>
      <td class="num" style="color:var(--gold); font-weight:600;">${pct(t.p_win_title)}</td>
    </tr>
  `).join("");
}

function renderAccuracy(accuracy) {
  const cards = document.getElementById("accuracy-cards");
  cards.innerHTML = accuracy.summary.map(s => `
    <div class="stat-card">
      <div class="label">${s.slice}</div>
      <div class="value">${s.n_matches > 0 ? pct(s.accuracy) : "\u2014"}</div>
      <div class="sub">${s.n_matches} matches${s.n_matches > 0 ? ` \u00b7 Brier ${s.mean_brier_score.toFixed(3)}` : ""}</div>
    </div>
  `).join("");

  const pendingEl = document.getElementById("pending-shootouts");
  if (accuracy.pending.length > 0) {
    pendingEl.innerHTML = `
      <div class="pending-banner">
        <strong>${accuracy.pending.length} match(es) awaiting a shootout winner</strong> --
        use the Add result tab to record who actually advanced.
        <ul>${accuracy.pending.map(p => `<li>${p.home_team} vs ${p.away_team}</li>`).join("")}</ul>
      </div>
    `;
  } else {
    pendingEl.innerHTML = "";
  }

  const thead = document.querySelector("#accuracy-log thead");
  const tbody = document.querySelector("#accuracy-log tbody");
  const resolved = accuracy.log.filter(r => r.actual_outcome);
  if (resolved.length === 0) {
    thead.innerHTML = "";
    tbody.innerHTML = `<tr><td class="muted">No resolved matches yet.</td></tr>`;
    return;
  }
  thead.innerHTML = `<tr><th>Date</th><th>Match</th><th>Predicted</th><th>Actual</th><th>Result</th></tr>`;
  tbody.innerHTML = resolved.slice().reverse().map(r => `
    <tr>
      <td>${formatDate(r.match_date)}</td>
      <td>${r.home_team} vs ${r.away_team}</td>
      <td>${r.predicted_winner}</td>
      <td>${r.actual_winner}</td>
      <td class="${String(r.correct) === "1" ? "correct-yes" : "correct-no"}">
        ${String(r.correct) === "1" ? "\u2713 Correct" : "\u2717 Missed"}
      </td>
    </tr>
  `).join("");
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// ---------- Add result form ----------

function renderAddResultTeams(predictions) {
  const teams = new Set();
  predictions.forEach(p => { teams.add(p.home_team); teams.add(p.away_team); });
  const sorted = Array.from(teams).sort();

  const homeSel = document.getElementById("home-team");
  const awaySel = document.getElementById("away-team");
  const shootoutSel = document.getElementById("shootout-winner");

  if (sorted.length === 0) return; // keep whatever /api/teams already populated

  const options = sorted.map(t => `<option value="${t}">${flag(t)} ${t}</option>`).join("");
  homeSel.innerHTML = `<option value="">Select team\u2026</option>${options}`;
  awaySel.innerHTML = `<option value="">Select team\u2026</option>${options}`;
}

async function populateTeamsFallback() {
  // Used on first load before any predictions exist, or once the
  // tournament is fully decided and predictions is empty.
  const res = await fetch("/api/teams");
  const body = await res.json();
  const options = body.teams.map(t => `<option value="${t}">${flag(t)} ${t}</option>`).join("");
  const homeSel = document.getElementById("home-team");
  const awaySel = document.getElementById("away-team");
  if (homeSel.children.length <= 1) homeSel.innerHTML = `<option value="">Select team\u2026</option>${options}`;
  if (awaySel.children.length <= 1) awaySel.innerHTML = `<option value="">Select team\u2026</option>${options}`;
}

function updateShootoutVisibility() {
  const homeScore = document.getElementById("home-score").value;
  const awayScore = document.getElementById("away-score").value;
  const row = document.getElementById("shootout-row");
  const isLevel = homeScore !== "" && awayScore !== "" && homeScore === awayScore;
  row.hidden = !isLevel;

  if (isLevel) {
    const homeTeam = document.getElementById("home-team").value;
    const awayTeam = document.getElementById("away-team").value;
    const sel = document.getElementById("shootout-winner");
    sel.innerHTML = `<option value="">Select the team that advanced\u2026</option>`
      + (homeTeam ? `<option value="${homeTeam}">${flag(homeTeam)} ${homeTeam}</option>` : "")
      + (awayTeam ? `<option value="${awayTeam}">${flag(awayTeam)} ${awayTeam}</option>` : "");
  }
}

async function handleAddResultSubmit(e) {
  e.preventDefault();
  const statusEl = document.getElementById("add-result-status");
  statusEl.textContent = "";
  statusEl.className = "form-status";

  const payload = {
    home: document.getElementById("home-team").value,
    away: document.getElementById("away-team").value,
    home_score: document.getElementById("home-score").value,
    away_score: document.getElementById("away-score").value,
    date: document.getElementById("match-date").value || null,
    neutral: document.getElementById("neutral-venue").checked,
    shootout_winner: document.getElementById("shootout-winner").value || null,
  };

  if (!payload.home || !payload.away) {
    statusEl.textContent = "Pick both teams.";
    statusEl.classList.add("error");
    return;
  }
  if (payload.home === payload.away) {
    statusEl.textContent = "Home and away can't be the same team.";
    statusEl.classList.add("error");
    return;
  }

  try {
    const res = await fetch("/api/add-result", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.message || "Couldn't save that result.");

    statusEl.textContent = "Result saved -- ratings and predictions updated.";
    statusEl.classList.add("success");
    document.getElementById("add-result-form").reset();
    document.getElementById("shootout-row").hidden = true;
    await refreshAll();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.classList.add("error");
  }
}

// ---------- Refresh button ----------

async function handleRefreshClick() {
  const btn = document.getElementById("refresh-btn");
  btn.classList.add("is-loading");
  btn.disabled = true;
  try {
    const res = await fetch("/api/update", { method: "POST" });
    const body = await res.json();
    if (!res.ok) throw new Error(body.message || "Refresh failed.");
    if (body.download_warning) {
      showToast(`Using cached data -- couldn't reach the data source (${body.download_warning})`, "error");
    } else {
      showToast("Data refreshed.", "success");
    }
    await refreshAll();
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    btn.classList.remove("is-loading");
    btn.disabled = false;
  }
}

// ---------- Toast ----------

let toastTimer = null;
function showToast(message, kind) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = `toast ${kind || ""}`;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 4000);
}

// ---------- Tabs ----------

function setupTabs() {
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
    });
  });
}

function setupPredictionFilters() {
  document.querySelectorAll("#prediction-filters .chip").forEach(chip => {
    chip.addEventListener("click", () => {
      document.querySelectorAll("#prediction-filters .chip").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      predictionFilter = chip.dataset.filter;
      if (latestSnapshot) renderPredictions(latestSnapshot.predictions);
    });
  });
}

// ---------- Init ----------

document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  setupPredictionFilters();
  document.getElementById("refresh-btn").addEventListener("click", handleRefreshClick);
  document.getElementById("add-result-form").addEventListener("submit", handleAddResultSubmit);
  document.getElementById("home-score").addEventListener("input", updateShootoutVisibility);
  document.getElementById("away-score").addEventListener("input", updateShootoutVisibility);
  document.getElementById("home-team").addEventListener("change", updateShootoutVisibility);
  document.getElementById("away-team").addEventListener("change", updateShootoutVisibility);

  refreshAll().then(() => populateTeamsFallback());
});
