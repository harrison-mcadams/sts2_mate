/**
 * Slay the Spire 2 Companion App - Client Controller
 */

let allCards = [];
let allRelics = [];
let currentState = null;

document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  setupAutocomplete();
  setupAdvisorActions();
  setupSyncButton();
  loadInitialData();
  fetchState(); // Immediate fetch on page load
  startLiveStream();
  setInterval(fetchState, 2500); // 2.5s heartbeat poll
});

// Tab Navigation
function setupTabs() {
  const tabs = document.querySelectorAll(".nav-tab");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");

      const targetPaneId = tab.dataset.tab;
      document.querySelectorAll(".tab-pane").forEach(pane => {
        pane.classList.remove("active");
      });
      document.getElementById(targetPaneId).classList.add("active");

      if (targetPaneId === "tabHistory") {
        loadHistoryStats();
      } else if (targetPaneId === "tabCompendium") {
        renderCompendium();
      }
    });
  });
}

// Initial Data Fetch
async function loadInitialData() {
  try {
    const res = await fetch("/api/cards");
    allCards = await res.json();

    const relicRes = await fetch("/api/relics");
    allRelics = await relicRes.json();
  } catch (err) {
    console.error("Failed loading card database:", err);
  }
}

// Immediate State Fetch
async function fetchState() {
  try {
    const res = await fetch("/api/state");
    const state = await res.json();
    if (state) {
      updateHUD(state);
      updateDeckAndRelics(state);
    }
  } catch (e) {
    console.warn("Poll state error:", e);
  }
}

// Real-Time Live Stream (SSE)
function startLiveStream() {
  try {
    const evtSource = new EventSource("/api/events");

    evtSource.onmessage = (event) => {
      try {
        const state = JSON.parse(event.data);
        if (state) {
          updateHUD(state);
          updateDeckAndRelics(state);
        }
      } catch (e) {
        console.error("Error parsing live stream event:", e);
      }
    };

    evtSource.onerror = () => {
      // EventSource failed or reconnected; polling will handle it
    };
  } catch (e) {
    console.warn("EventSource not supported; polling active.");
  }
}

// Update HUD Elements
function updateHUD(state) {
  currentState = state;
  const statusBadge = document.getElementById("statusBadge");
  const statusText = document.getElementById("statusText");

  if (!state) return;

  if (state.is_active || state.game_status === "RUN_ACTIVE") {
    statusBadge.className = "status-badge live";
    statusText.textContent = "LIVE RUN ACTIVE";
  } else if (state.game_status === "MAIN_MENU") {
    statusBadge.className = "status-badge idle";
    statusText.textContent = "AT MAIN MENU (EMBARK ON RUN TO TRACK)";
  } else if (state.waiting_for_game || state.game_status === "WAITING_FOR_GAME") {
    statusBadge.className = "status-badge idle";
    statusText.textContent = "WAITING FOR STS2 TO START";
  } else {
    statusBadge.className = "status-badge idle";
    statusText.textContent = "IDLE (SHOWING LATEST RUN)";
  }

  // Update hero styling class on body
  const char = (state.character || "Ironclad").toLowerCase();
  document.body.className = `char-${char}`;

  document.getElementById("valChar").textContent = state.character || "IRONCLAD";
  document.getElementById("valAsc").textContent = `A${state.ascension || 0}`;
  
  if ((state.waiting_for_game || state.game_status === "MAIN_MENU") && (!state.current_floor || state.current_floor === 0)) {
    document.getElementById("valFloor").textContent = "Not in run";
  } else {
    document.getElementById("valFloor").textContent = `Floor ${state.current_floor || 1} (Act ${state.current_act || 1})`;
  }

  const curHp = state.current_hp || 0;
  const maxHp = state.max_hp || 1;
  const hpPct = Math.min(100, Math.max(0, state.hp_percent || (curHp / maxHp * 100)));
  document.getElementById("valHp").textContent = `${curHp} / ${maxHp}`;
  document.getElementById("hpBarFill").style.width = `${hpPct}%`;

  document.getElementById("valGold").textContent = `${state.gold || 0} 🪙`;
  const deckSize = state.deck_size || (state.deck ? state.deck.length : 0);
  document.getElementById("valDeckSize").textContent = `${deckSize} Cards`;
  document.getElementById("deckTabCount").textContent = deckSize;

  // Check pending card reward
  const notice = document.getElementById("pendingRewardNotice");
  if (state.is_active && state.pending_reward && state.pending_reward.length > 0) {
    notice.classList.remove("hidden");
  } else {
    notice.classList.add("hidden");
  }
}

// Update Deck and Relics Tab
function updateDeckAndRelics(state) {
  if (!state) return;

  // Relics
  const relicsList = document.getElementById("relicsList");
  relicsList.innerHTML = "";
  const relics = state.relics || [];
  document.getElementById("relicCount").textContent = relics.length;

  relics.forEach(r => {
    const chip = document.createElement("div");
    chip.className = "relic-chip";
    chip.innerHTML = `
      <span>🧿</span>
      <span>${escapeHtml(r.name)}</span>
      <div class="tooltip">
        <strong>${escapeHtml(r.name)}</strong><br>
        ${escapeHtml(r.description || "No description available.")}
        ${r.flavor ? `<br><em style="color:#94a3b8;font-size:0.75rem;">"${escapeHtml(r.flavor)}"</em>` : ""}
      </div>
    `;
    relicsList.appendChild(chip);
  });

  // Deck counts
  const breakdown = state.deck_breakdown || {};
  document.getElementById("cntAttacks").textContent = breakdown["Attack"] || 0;
  document.getElementById("cntSkills").textContent = breakdown["Skill"] || 0;
  document.getElementById("cntPowers").textContent = breakdown["Power"] || 0;
  document.getElementById("cntCurses").textContent = (breakdown["Curse"] || 0) + (breakdown["Status"] || 0);

  // Deck cards aggregated by count
  const deckCardsGrid = document.getElementById("deckCardsGrid");
  deckCardsGrid.innerHTML = "";

  const deck = state.deck || [];
  const cardCounts = {};
  deck.forEach(c => {
    const key = c.display_name || c.name;
    if (!cardCounts[key]) {
      cardCounts[key] = { card: c, count: 0 };
    }
    cardCounts[key].count++;
  });

  Object.values(cardCounts).forEach(({ card, count }) => {
    const item = document.createElement("div");
    item.className = "deck-card-item";
    const typeClass = `type-${card.card_type || "Skill"}`;

    item.innerHTML = `
      <div class="card-header">
        <span class="card-name">${escapeHtml(card.display_name || card.name)}</span>
        <span class="card-count-badge">x${count}</span>
      </div>
      <span class="card-type-tag ${typeClass}">${escapeHtml(card.card_type || "Card")}</span>
      <div class="card-desc">${escapeHtml(card.description || "")}</div>
    `;
    deckCardsGrid.appendChild(item);
  });
}

// Card Reward Autocomplete
function setupAutocomplete() {
  const slots = [1, 2, 3, 4];

  slots.forEach(num => {
    const input = document.getElementById(`slot${num}`);
    const dropdown = document.getElementById(`dropdown${num}`);

    input.addEventListener("input", () => {
      const val = input.value.trim().toLowerCase();
      if (!val) {
        dropdown.style.display = "none";
        return;
      }

      const matches = allCards.filter(c =>
        c.name.toLowerCase().includes(val) || c.key.toLowerCase().includes(val)
      ).slice(0, 10);

      dropdown.innerHTML = "";
      if (matches.length === 0) {
        dropdown.style.display = "none";
        return;
      }

      matches.forEach(c => {
        const item = document.createElement("div");
        item.className = "autocomplete-item";
        item.innerHTML = `
          <span>${escapeHtml(c.name)}</span>
          <span class="card-char">${escapeHtml(c.character)}</span>
        `;
        item.addEventListener("click", () => {
          input.value = c.name;
          dropdown.style.display = "none";
        });
        dropdown.appendChild(item);
      });

      dropdown.style.display = "block";
    });

    document.addEventListener("click", (e) => {
      if (!input.contains(e.target) && !dropdown.contains(e.target)) {
        dropdown.style.display = "none";
      }
    });
  });
}

// Advisor Actions
function setupAdvisorActions() {
  const btnEvaluate = document.getElementById("btnEvaluate");
  const btnClear = document.getElementById("btnClearSlots");
  const btnLoadPending = document.getElementById("btnLoadPending");

  btnEvaluate.addEventListener("click", runEvaluation);

  btnClear.addEventListener("click", () => {
    [1, 2, 3, 4].forEach(n => {
      document.getElementById(`slot${n}`).value = "";
    });
    document.getElementById("adviceResultsArea").classList.add("hidden");
  });

  btnLoadPending.addEventListener("click", () => {
    if (currentState && currentState.pending_reward) {
      currentState.pending_reward.forEach((c, idx) => {
        if (idx < 4) {
          document.getElementById(`slot${idx + 1}`).value = c.name;
        }
      });
      runEvaluation();
    }
  });
}

async function runEvaluation() {
  const cards = [];
  [1, 2, 3, 4].forEach(n => {
    const val = document.getElementById(`slot${n}`).value.trim();
    if (val) cards.push(val);
  });

  if (cards.length === 0) {
    alert("Please enter at least one card name to evaluate.");
    return;
  }

  try {
    const res = await fetch("/api/advise", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cards }),
    });
    const data = await res.json();
    renderAdviceResults(data);
  } catch (err) {
    console.error("Evaluation failed:", err);
    alert("Failed to evaluate card choices.");
  }
}

function renderAdviceResults(data) {
  const resultsArea = document.getElementById("adviceResultsArea");
  const banner = document.getElementById("verdictBanner");
  const icon = document.getElementById("verdictIcon");
  const title = document.getElementById("verdictTitle");
  const sub = document.getElementById("verdictSub");
  const grid = document.getElementById("rankedCardsGrid");

  resultsArea.classList.remove("hidden");

  if (data.should_skip) {
    banner.className = "verdict-banner skip";
    icon.textContent = "🛑";
    title.textContent = "RECOMMENDATION: SKIP CARD REWARD";
    sub.textContent = data.verdict;
  } else {
    banner.className = "verdict-banner";
    icon.textContent = "🏆";
    title.textContent = `RECOMMENDED: Pick ${data.top_choice}`;
    sub.textContent = data.verdict;
  }

  grid.innerHTML = "";
  const options = data.ranked_options || [];

  options.forEach((opt, idx) => {
    const c = opt.card;
    const cardEl = document.createElement("div");
    cardEl.className = `ranked-card ${idx === 0 && !data.should_skip ? "top-choice" : ""}`;

    const prosHtml = opt.pros.map(p => `<div class="pro-item"><span>+</span><span>${escapeHtml(p)}</span></div>`).join("");
    const consHtml = opt.cons.map(c => `<div class="con-item"><span>-</span><span>${escapeHtml(c)}</span></div>`).join("");

    let pStatHtml = "";
    if (opt.personal_stats) {
      const ps = opt.personal_stats;
      pStatHtml = `<div class="personal-stat-tag">📊 Your Stats: ${ps.win_rate}% Win Rate (${ps.drafted_runs} runs) | Picked ${ps.pick_rate}%</div>`;
    }

    cardEl.innerHTML = `
      <div class="ranked-card-header">
        <div>
          <span class="ranked-card-title">${escapeHtml(c.name)}</span><br>
          <span class="card-type-tag type-${c.card_type}">${escapeHtml(c.card_type || "Card")} (${escapeHtml(c.character || "all")})</span>
        </div>
        <div class="score-badge">${opt.score.toFixed(1)}</div>
      </div>
      <div class="card-description-box">${escapeHtml(c.description || "No text")}</div>
      <div class="reasoning-list">
        ${prosHtml}
        ${consHtml}
        <div style="font-size:0.75rem; color:#94a3b8; margin-top:4px;">
          Upgrade Priority: <strong style="color:#e2e8f0;">${escapeHtml(opt.upgrade_priority)}</strong>
        </div>
      </div>
      ${pStatHtml}
    `;
    grid.appendChild(cardEl);
  });
}

// Player History & Stats
async function loadHistoryStats() {
  try {
    const res = await fetch("/api/stats");
    const data = await res.json();

    document.getElementById("statTotalRuns").textContent = data.total_runs || 0;
    document.getElementById("statTotalWins").textContent = data.total_wins || 0;
    document.getElementById("statWinRate").textContent = `${data.overall_win_rate || 0}%`;

    // Character stats
    const charList = document.getElementById("characterStatsList");
    charList.innerHTML = "";
    Object.values(data.characters || {}).forEach(cs => {
      const row = document.createElement("div");
      row.className = "char-row";
      row.innerHTML = `
        <strong>${escapeHtml(cs.character)}</strong>
        <span>${cs.runs} runs (${cs.win_rate}% wins) | Max A${cs.highest_ascension}</span>
      `;
      charList.appendChild(row);
    });

    // Lethal encounters
    const lethalList = document.getElementById("lethalEncountersList");
    lethalList.innerHTML = "";
    (data.top_lethal_encounters || []).slice(0, 6).forEach(([enc, count]) => {
      const cleanEnc = enc.replace("ENCOUNTER.", "").replace("_", " ").title ? enc.replace("ENCOUNTER.", "").toLowerCase().replace(/_/g, " ") : enc;
      const row = document.createElement("div");
      row.className = "lethal-row";
      row.innerHTML = `
        <span style="text-transform:capitalize;">${escapeHtml(cleanEnc)}</span>
        <span style="color:#f87171;font-weight:700;">${count} Deaths</span>
      `;
      lethalList.appendChild(row);
    });

    // Recent runs table
    const tbody = document.getElementById("recentRunsTbody");
    tbody.innerHTML = "";
    (data.recent_runs || []).forEach(r => {
      const tr = document.createElement("tr");
      const outcomeClass = r.win ? "outcome-win" : "outcome-loss";
      const outcomeText = r.win ? "VICTORY" : "DEFEAT";
      const killed = r.killed_by && r.killed_by !== "NONE" ? r.killed_by.replace("ENCOUNTER.", "").toLowerCase().replace(/_/g, " ") : "-";

      tr.innerHTML = `
        <td><strong>${escapeHtml(r.character)}</strong></td>
        <td>A${r.ascension}</td>
        <td>${r.floor}</td>
        <td class="${outcomeClass}">${outcomeText}</td>
        <td style="text-transform:capitalize;">${escapeHtml(killed)}</td>
        <td>${r.deck_size}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Failed loading player stats:", err);
  }
}

// Compendium Search and Filter
function renderCompendium() {
  const search = document.getElementById("compSearch");
  const charFilter = document.getElementById("compCharFilter");
  const grid = document.getElementById("compendiumGrid");

  function filter() {
    const q = search.value.trim().toLowerCase();
    const char = charFilter.value.toLowerCase();

    const filtered = allCards.filter(c => {
      if (char && c.character.toLowerCase() !== char && c.character !== "colorless") return false;
      if (q && !c.name.toLowerCase().includes(q) && !c.description.toLowerCase().includes(q)) return false;
      return true;
    }).slice(0, 48);

    grid.innerHTML = "";
    filtered.forEach(c => {
      const cardEl = document.createElement("div");
      cardEl.className = "comp-card";
      cardEl.innerHTML = `
        <div class="comp-card-header">
          <span class="comp-card-name">${escapeHtml(c.name)}</span>
          <span class="card-type-tag type-${c.card_type}">${escapeHtml(c.card_type)}</span>
        </div>
        <div style="font-size:0.75rem; color:#94a3b8; text-transform:capitalize;">${escapeHtml(c.character)}</div>
        <div class="comp-card-desc">${escapeHtml(c.description || "")}</div>
      `;
      grid.appendChild(cardEl);
    });
  }

  search.oninput = filter;
  charFilter.onchange = filter;
  filter();
}

// Sync Database Button
function setupSyncButton() {
  const btn = document.getElementById("btnSyncDb");
  btn.addEventListener("click", async () => {
    btn.textContent = "Syncing...";
    btn.disabled = true;
    try {
      const res = await fetch("/api/sync", { method: "POST" });
      const data = await res.json();
      if (data.success) {
        alert("Database successfully re-synced directly from Slay the Spire 2 files!");
        await loadInitialData();
      } else {
        alert("Sync error: " + data.error);
      }
    } catch (e) {
      alert("Failed to sync database: " + e);
    } finally {
      btn.innerHTML = `<span class="icon">🔄</span> Re-sync DB`;
      btn.disabled = false;
    }
  });
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
