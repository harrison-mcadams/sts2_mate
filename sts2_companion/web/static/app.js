/**
 * Slay the Spire 2 Companion App - Client Controller
 */

let allCards = [];
let allRelics = [];
let currentState = null;
let currentChatHistory = [];
let lastEvaluatedCards = [];
let lastAIRec = null;

document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  setupAutocomplete();
  setupAdvisorActions();
  setupAIChat();
  setupDeckCoachActions();
  setupSettingsModal();
  setupSyncButton();
  loadInitialData();
  checkApiKeyStatus();
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
      } else if (targetPaneId === "tabDeck") {
        loadDeckAnalysis();
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

  // Auto-recognize and evaluate pending card rewards
  handleAutoRewardEvaluation(state);
}

let lastAutoEvaluatedKey = "";

function handleAutoRewardEvaluation(state) {
  const notice = document.getElementById("pendingRewardNotice");
  if (!state || !state.is_active || !state.pending_reward || state.pending_reward.length === 0) {
    if (notice) notice.classList.add("hidden");
    return;
  }

  const rewardCards = state.pending_reward;
  const rewardKey = rewardCards.map(c => c.id || c.name).sort().join("|");

  if (notice) {
    notice.classList.remove("hidden");
    const cardNames = rewardCards.map(c => c.name || c.id).join(" • ");
    const span = notice.querySelector("span");
    if (span) span.innerHTML = `🎁 <strong>Live Reward Offered:</strong> ${escapeHtml(cardNames)}`;
  }

  // If this reward set has not been evaluated yet, auto-evaluate!
  if (rewardKey !== lastAutoEvaluatedKey) {
    lastAutoEvaluatedKey = rewardKey;

    [1, 2, 3, 4].forEach(n => {
      const input = document.getElementById(`slot${n}`);
      if (input) input.value = "";
    });

    rewardCards.forEach((c, idx) => {
      if (idx < 4) {
        const input = document.getElementById(`slot${idx + 1}`);
        if (input) input.value = c.name || c.id;
      }
    });

    // Auto-switch to Advisor tab so the player sees it immediately
    const advisorTab = document.querySelector('.nav-tab[data-tab="tabAdvisor"]');
    if (advisorTab && !advisorTab.classList.contains("active")) {
      advisorTab.click();
    }

    // Automatically trigger evaluation
    runEvaluation();
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

// ==========================================
// GEMINI DECK ENGINE & PILOT COACH
// ==========================================
let currentDeckAnalysis = null;
let deckChatHistory = [];

async function loadDeckAnalysis(forceRefresh = false) {
  const btn = document.getElementById("btnAnalyzeDeck");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span>⏳</span> Analyzing Deck...`;
  }

  try {
    const res = await fetch("/api/deck_analysis", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force_refresh: forceRefresh }),
    });
    const result = await res.json();
    if (result.success && result.data) {
      currentDeckAnalysis = result;
      renderDeckAnalysis(result);
    } else {
      console.warn("Deck analysis note:", result.error);
      const nameEl = document.getElementById("deckBuildName");
      if (nameEl) nameEl.textContent = result.error || "No active run detected";
    }
  } catch (err) {
    console.error("Failed to load deck analysis:", err);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<span>✨</span> Analyze Deck with Gemini`;
    }
  }
}

function renderDeckAnalysis(result) {
  const data = result.data || {};
  const stageEl = document.getElementById("deckBuildStage");
  const nameEl = document.getElementById("deckBuildName");
  const winconEl = document.getElementById("deckWinCondition");
  const modelBadge = document.getElementById("deckEngineModelBadge");

  if (stageEl) stageEl.textContent = data.build_stage || "CORE ENGINE FORMING";
  if (nameEl) nameEl.textContent = data.build_name || "Archetype Identified";
  if (winconEl) winconEl.textContent = data.core_win_condition || "Focus on compounding your card synergies and survivability.";
  if (modelBadge) {
    modelBadge.textContent = result.provider === "gemini" ? (result.model || "Gemini 2.5 Flash") : "Local Heuristic Engine";
  }

  // Playbook
  const turnPriority = document.getElementById("coachTurnPriority");
  if (turnPriority) turnPriority.textContent = data.playbook?.turn_1_2_priority || "Prioritize powers and vulnerable inflicters.";

  const seqList = document.getElementById("coachSequencingList");
  if (seqList) {
    seqList.innerHTML = (data.playbook?.key_sequencing || []).map(s => `<li>${escapeHtml(s)}</li>`).join("");
  }

  const mitRule = document.getElementById("coachMitigationRule");
  if (mitRule) mitRule.textContent = data.playbook?.mitigation_rule || "Balance block and attack based on incoming intent.";

  // What to look for
  const cardsList = document.getElementById("coachPriorityCards");
  if (cardsList) {
    cardsList.innerHTML = (data.what_to_look_for?.priority_cards || []).map(c => `
      <div class="coach-item-chip"><strong>${escapeHtml(c.card_name)}</strong>: ${escapeHtml(c.why)}</div>
    `).join("");
  }

  const relicsList = document.getElementById("coachPriorityRelics");
  if (relicsList) {
    relicsList.innerHTML = (data.what_to_look_for?.priority_relics || []).map(r => `
      <div class="coach-item-chip"><strong>${escapeHtml(r.relic_name)}</strong>: ${escapeHtml(r.why)}</div>
    `).join("");
  }

  const potionsList = document.getElementById("coachPriorityPotions");
  if (potionsList) {
    potionsList.innerHTML = (data.what_to_look_for?.priority_potions || []).map(p => `
      <div class="coach-item-chip"><strong>${escapeHtml(p.potion_name)}</strong>: ${escapeHtml(p.why)}</div>
    `).join("");
  }

  // What to avoid
  const avoidList = document.getElementById("coachAvoidList");
  if (avoidList) {
    avoidList.innerHTML = (data.what_to_avoid || []).map(a => `
      <div class="coach-avoid-item">
        <strong>⚠️ ${escapeHtml(a.target)}</strong>
        <span>${escapeHtml(a.danger_reason)}</span>
      </div>
    `).join("");
  }

  // Boss & Purge
  const bossAssessment = document.getElementById("coachBossAssessment");
  if (bossAssessment) bossAssessment.textContent = data.boss_matchup?.threat_assessment || "-";

  const purgeList = document.getElementById("coachPurgeList");
  if (purgeList) {
    purgeList.innerHTML = (data.card_removal_priority || []).map(p => `
      <div class="coach-purge-item">
        <strong>🗑️ ${escapeHtml(p.card_name)}</strong>: ${escapeHtml(p.reason)}
      </div>
    `).join("");
  }
}

function setupDeckCoachActions() {
  const btnAnalyze = document.getElementById("btnAnalyzeDeck");
  if (btnAnalyze) {
    btnAnalyze.addEventListener("click", () => loadDeckAnalysis(true));
  }

  // Suggestion chips
  document.querySelectorAll(".deck-suggest-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const q = chip.dataset.q;
      const input = document.getElementById("deckChatInput");
      if (input) {
        input.value = q;
        sendDeckChatMessage();
      }
    });
  });

  // Send message
  const btnSend = document.getElementById("btnSendDeckChat");
  const input = document.getElementById("deckChatInput");
  if (btnSend && input) {
    btnSend.addEventListener("click", sendDeckChatMessage);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") sendDeckChatMessage();
    });
  }
}

async function sendDeckChatMessage() {
  const input = document.getElementById("deckChatInput");
  const btn = document.getElementById("btnSendDeckChat");
  const msgContainer = document.getElementById("deckChatMessages");
  if (!input || !msgContainer) return;

  const text = input.value.trim();
  if (!text) return;

  // Render user message
  const userMsgEl = document.createElement("div");
  userMsgEl.className = "ai-chat-msg user";
  userMsgEl.innerHTML = `<div class="msg-bubble">${escapeHtml(text)}</div>`;
  msgContainer.appendChild(userMsgEl);
  input.value = "";
  msgContainer.scrollTop = msgContainer.scrollHeight;

  // Render loading placeholder
  const loadingEl = document.createElement("div");
  loadingEl.className = "ai-chat-msg ai";
  loadingEl.innerHTML = `<div class="msg-bubble ai-loading">Strategist is thinking...</div>`;
  msgContainer.appendChild(loadingEl);
  msgContainer.scrollTop = msgContainer.scrollHeight;

  if (btn) btn.disabled = true;

  try {
    const res = await fetch("/api/deck_chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        history: deckChatHistory,
      }),
    });
    const result = await res.json();
    loadingEl.remove();

    const aiMsgEl = document.createElement("div");
    aiMsgEl.className = "ai-chat-msg ai";

    if (result.success && result.reply) {
      aiMsgEl.innerHTML = `<div class="msg-bubble">${escapeHtml(result.reply)}</div>`;
      deckChatHistory.push({ role: "user", content: text });
      deckChatHistory.push({ role: "model", content: result.reply });
    } else {
      aiMsgEl.innerHTML = `<div class="msg-bubble error">⚠️ ${escapeHtml(result.error || "Failed to get reply.")}</div>`;
    }
    msgContainer.appendChild(aiMsgEl);
    msgContainer.scrollTop = msgContainer.scrollHeight;
  } catch (err) {
    loadingEl.remove();
    const aiMsgEl = document.createElement("div");
    aiMsgEl.className = "ai-chat-msg ai";
    aiMsgEl.innerHTML = `<div class="msg-bubble error">⚠️ Network error: ${escapeHtml(err.message)}</div>`;
    msgContainer.appendChild(aiMsgEl);
  } finally {
    if (btn) btn.disabled = false;
  }
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

      const currentChar = currentState && currentState.character ? currentState.character.toLowerCase() : "";

      const matches = allCards.filter(c =>
        c.name.toLowerCase().includes(val) || c.key.toLowerCase().includes(val)
      ).sort((a, b) => {
        const aChar = (a.character || "").toLowerCase() === currentChar ? 0 : 1;
        const bChar = (b.character || "").toLowerCase() === currentChar ? 0 : 1;
        if (aChar !== bChar) return aChar - bChar;
        const aStarts = a.name.toLowerCase().startsWith(val) ? 0 : 1;
        const bStarts = b.name.toLowerCase().startsWith(val) ? 0 : 1;
        if (aStarts !== bStarts) return aStarts - bStarts;
        return a.name.localeCompare(b.name);
      }).slice(0, 10);

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

          // Auto-advance to next empty slot
          if (num < 3) {
            const nextInput = document.getElementById(`slot${num + 1}`);
            if (nextInput && !nextInput.value) {
              nextInput.focus();
            }
          }
          checkAutoEvaluate();
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

function checkAutoEvaluate() {
  const s1 = document.getElementById("slot1").value.trim();
  const s2 = document.getElementById("slot2").value.trim();
  const s3 = document.getElementById("slot3").value.trim();
  if (s1 && s2 && s3) {
    runEvaluation();
  }
}

// Advisor Actions
function setupAdvisorActions() {
  const btnEvaluate = document.getElementById("btnEvaluate");
  const btnClear = document.getElementById("btnClearSlots");
  const btnLoadPending = document.getElementById("btnLoadPending");
  const btnScreenGrab = document.getElementById("btnScreenGrab");
  const btnAskAI = document.getElementById("btnAskAI");
  const btnOpenKeyModal = document.getElementById("btnOpenKeyModal");

  btnEvaluate.addEventListener("click", runEvaluation);

  if (btnAskAI) {
    btnAskAI.addEventListener("click", runAIEvaluation);
  }

  if (btnOpenKeyModal) {
    btnOpenKeyModal.addEventListener("click", openSettingsModal);
  }

  if (btnScreenGrab) {
    btnScreenGrab.addEventListener("click", runScreenGrab);
  }

  // Hotkey: Press 'G' to grab screen
  document.addEventListener("keydown", (e) => {
    if (e.key.toLowerCase() === "g" && !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) {
      e.preventDefault();
      if (btnScreenGrab) btnScreenGrab.click();
    }
  });

  const btnRetryAI = document.getElementById("btnRetryAI");
  if (btnRetryAI) {
    btnRetryAI.addEventListener("click", runAIEvaluation);
  }

  const btnConfigAI = document.getElementById("btnConfigAI");
  if (btnConfigAI) {
    btnConfigAI.addEventListener("click", openSettingsModal);
  }

  btnClear.addEventListener("click", () => {
    [1, 2, 3, 4].forEach(n => {
      document.getElementById(`slot${n}`).value = "";
    });
    document.getElementById("adviceResultsArea").classList.add("hidden");
    const aiCard = document.getElementById("aiAdvisorCard");
    if (aiCard) aiCard.classList.add("hidden");
    const aiErrorNotice = document.getElementById("aiErrorNotice");
    if (aiErrorNotice) aiErrorNotice.classList.add("hidden");
    const notice = document.getElementById("grabStatusNotice");
    if (notice) notice.classList.add("hidden");

    currentChatHistory = [];
    lastEvaluatedCards = [];
    lastAIRec = null;
    const chatMsgs = document.getElementById("aiChatMessages");
    if (chatMsgs) chatMsgs.innerHTML = "";
    const chatSugg = document.getElementById("aiChatSuggestions");
    if (chatSugg) chatSugg.innerHTML = "";
    const chatInput = document.getElementById("aiChatInput");
    if (chatInput) chatInput.value = "";
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

let isApiKeyConfigured = false;

async function checkApiKeyStatus() {
  try {
    const res = await fetch("/api/config");
    const data = await res.json();
    isApiKeyConfigured = !!data.gemini_api_key_configured;
  } catch (e) {
    console.warn("Failed checking API key status:", e);
  }
}

async function runScreenGrab() {
  const btn = document.getElementById("btnScreenGrab");
  const notice = document.getElementById("grabStatusNotice");
  if (!btn) return;

  btn.classList.add("loading");
  btn.innerHTML = `<span>⏳</span> Scanning Screen...`;
  if (notice) {
    notice.className = "grab-notice";
    notice.innerText = "Capturing screen & running OCR...";
    notice.classList.remove("hidden");
  }

  try {
    const res = await fetch("/api/screen_grab", { method: "POST" });
    const data = await res.json();

    if (!res.ok || !data.success) {
      if (notice) {
        notice.className = "grab-notice error";
        notice.innerText = `❌ ${data.error || "Screen grab failed. Ensure game is running on PC."}`;
      }
      return;
    }

    const cards = data.cards || [];
    if (cards.length === 0) {
      if (notice) {
        notice.className = "grab-notice warning";
        notice.innerText = `⚠️ No card rewards detected on screen. Make sure the 3-card reward screen is open in STS2!`;
      }
      return;
    }

    // Populate slots
    [1, 2, 3, 4].forEach(n => {
      document.getElementById(`slot${n}`).value = "";
    });

    cards.forEach((c, idx) => {
      if (idx < 4) {
        document.getElementById(`slot${idx + 1}`).value = c.name;
      }
    });

    if (data.evaluation) {
      renderAdviceResults(data.evaluation);
    } else {
      runEvaluation();
    }

    if (data.ai_evaluation) {
      renderAIAdvice(data.ai_evaluation);
    }

    if (notice) {
      notice.className = "grab-notice success";
      const names = cards.map(c => c.name).join(", ");
      notice.innerText = `✅ Detected ${cards.length} cards: ${names}! Evaluated instantly.`;
    }
  } catch (err) {
    console.error("Screen grab request failed:", err);
    if (notice) {
      notice.className = "grab-notice error";
      notice.innerText = `❌ Error communicating with screen grab service: ${err.message}`;
    }
  } finally {
    btn.classList.remove("loading");
    btn.innerHTML = `<span>📸</span> Grab Screen (PC)`;
  }
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

    // If key configured, run AI evaluation automatically
    if (isApiKeyConfigured) {
      runAIEvaluation();
    }
  } catch (err) {
    console.error("Evaluation failed:", err);
    alert("Failed to evaluate card choices.");
  }
}

async function runAIEvaluation() {
  const cards = [];
  [1, 2, 3, 4].forEach(n => {
    const val = document.getElementById(`slot${n}`).value.trim();
    if (val) cards.push(val);
  });

  if (cards.length === 0) {
    alert("Please enter at least one card name to evaluate.");
    return;
  }

  lastEvaluatedCards = [...cards];
  currentChatHistory = [];
  const chatMsgs = document.getElementById("aiChatMessages");
  if (chatMsgs) chatMsgs.innerHTML = "";

  const btnAskAI = document.getElementById("btnAskAI");
  const aiCard = document.getElementById("aiAdvisorCard");
  const keyNotice = document.getElementById("aiKeyNotice");
  const aiErrorNotice = document.getElementById("aiErrorNotice");
  const aiErrorMessage = document.getElementById("aiErrorMessage");
  const resultsArea = document.getElementById("adviceResultsArea");

  resultsArea.classList.remove("hidden");
  if (aiErrorNotice) aiErrorNotice.classList.add("hidden");
  if (keyNotice) keyNotice.classList.add("hidden");

  if (btnAskAI) {
    btnAskAI.classList.add("loading");
    btnAskAI.innerHTML = `<span>⏳</span> Consulting Gemini AI...`;
  }

  try {
    const res = await fetch("/api/ai_evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cards }),
    });
    const data = await res.json();

    if (data.fallback_evaluation) {
      renderAdviceResults(data.fallback_evaluation);
    }

    if (!data.success) {
      if (data.requires_api_key) {
        if (keyNotice) keyNotice.classList.remove("hidden");
        if (aiCard) aiCard.classList.add("hidden");
        return;
      }
      if (aiErrorNotice && aiErrorMessage) {
        aiErrorMessage.textContent = data.error || "Gemini evaluation could not be completed.";
        aiErrorNotice.classList.remove("hidden");
      }
      if (aiCard) aiCard.classList.add("hidden");
      return;
    }

    renderAIAdvice(data);
  } catch (err) {
    console.error("AI Evaluation error:", err);
    if (aiErrorNotice && aiErrorMessage) {
      aiErrorMessage.textContent = `Communication error with companion server: ${err.message || err}`;
      aiErrorNotice.classList.remove("hidden");
    }
    if (aiCard) aiCard.classList.add("hidden");
  } finally {
    if (btnAskAI) {
      btnAskAI.classList.remove("loading");
      btnAskAI.innerHTML = `<span>🧠</span> Ask Gemini AI`;
    }
  }
}

function renderAIAdvice(data) {
  const aiCard = document.getElementById("aiAdvisorCard");
  const keyNotice = document.getElementById("aiKeyNotice");
  const aiErrorNotice = document.getElementById("aiErrorNotice");
  if (!aiCard) return;

  if (!data || !data.success || !data.recommendation) {
    if (data && data.requires_api_key && keyNotice) {
      keyNotice.classList.remove("hidden");
      aiCard.classList.add("hidden");
    }
    return;
  }

  if (keyNotice) keyNotice.classList.add("hidden");
  if (aiErrorNotice) aiErrorNotice.classList.add("hidden");
  aiCard.classList.remove("hidden");

  const rec = data.recommendation;
  lastAIRec = rec;

  const modelBadge = document.getElementById("aiModelBadge");
  if (modelBadge) modelBadge.textContent = data.model || "Gemini Flash";

  const groundingBadge = document.getElementById("aiGroundingBadge");
  if (groundingBadge) {
    if (data.grounding_active) {
      groundingBadge.textContent = "🔍 Web Grounded";
      groundingBadge.style.display = "inline-block";
    } else {
      groundingBadge.textContent = "📦 STS2 DB & Save Grounded";
      groundingBadge.style.display = "inline-block";
    }
  }

  const headline = document.getElementById("aiVerdictHeadline");
  if (headline) headline.textContent = rec.verdict || `Recommended: ${rec.recommended_card}`;

  const reasoning = document.getElementById("aiReasoning");
  if (reasoning) reasoning.textContent = rec.tactical_reasoning || "";

  const threatPrep = document.getElementById("aiThreatPrep");
  if (threatPrep) threatPrep.textContent = rec.upcoming_threat_prep || "General deck balance preparation.";

  const synergiesUl = document.getElementById("aiSynergies");
  if (synergiesUl) {
    synergiesUl.innerHTML = "";
    const syns = rec.deck_synergies || [];
    if (syns.length === 0) {
      synergiesUl.innerHTML = "<li>No direct synergistic dependencies. Good standalone addition.</li>";
    } else {
      syns.forEach(s => {
        const li = document.createElement("li");
        li.textContent = s;
        synergiesUl.appendChild(li);
      });
    }
  }

  // --- UNIFY MAIN RECOMMENDATION THROUGHLINE WITH GEMINI ---
  // 1. Top Verdict Banner
  const banner = document.getElementById("verdictBanner");
  const verdictIcon = document.getElementById("verdictIcon");
  const verdictTitle = document.getElementById("verdictTitle");
  const verdictSub = document.getElementById("verdictSub");

  if (banner && verdictTitle) {
    if (rec.should_skip) {
      banner.className = "verdict-banner skip";
      if (verdictIcon) verdictIcon.textContent = "🛑";
      verdictTitle.textContent = "RECOMMENDATION: SKIP CARD REWARD";
      if (verdictSub) verdictSub.textContent = rec.verdict || "Gemini advises skipping this reward to protect deck density.";
    } else {
      banner.className = "verdict-banner";
      if (verdictIcon) verdictIcon.textContent = "🏆";
      verdictTitle.textContent = `RECOMMENDED: Pick ${rec.recommended_card}`;
      if (verdictSub) verdictSub.textContent = rec.verdict || "";
    }
  }

  // 2. Ranked Cards Grid: Reassign glowing gold .top-choice and attach Gemini tier badges/notes
  const rankedCards = document.querySelectorAll(".ranked-card");
  const cardEvaluations = rec.card_evaluations || [];
  const evalMap = {};
  cardEvaluations.forEach(ce => {
    if (ce.name) evalMap[ce.name.toLowerCase()] = ce;
  });

  rankedCards.forEach(cardEl => {
    const nameEl = cardEl.querySelector(".card-name");
    if (!nameEl) return;
    const cardName = nameEl.textContent.trim().toLowerCase();

    // Reassign top-choice highlight
    const isTopChoice = !rec.should_skip && (cardName === (rec.recommended_card || "").toLowerCase());
    if (isTopChoice) {
      cardEl.classList.add("top-choice");
    } else {
      cardEl.classList.remove("top-choice");
    }

    // Clean any prior AI badge/notes
    const prevBadge = cardEl.querySelector(".ai-tier-badge");
    if (prevBadge) prevBadge.remove();
    const prevNote = cardEl.querySelector(".ai-card-note");
    if (prevNote) prevNote.remove();

    // Find Gemini evaluation for this card
    const cardEval = evalMap[cardName];
    if (cardEval) {
      const tier = cardEval.verdict_tier || (isTopChoice ? "Top Pick" : "Situational");
      let tierClass = "tier-situational";
      const tLower = tier.toLowerCase();
      if (tLower.includes("top")) tierClass = "tier-top-pick";
      else if (tLower.includes("dilut")) tierClass = "tier-dilution";
      else if (tLower.includes("skip")) tierClass = "tier-skip";

      const badgeEl = document.createElement("span");
      badgeEl.className = `ai-tier-badge ${tierClass}`;
      badgeEl.textContent = tier;
      const headerEl = cardEl.querySelector(".card-header");
      if (headerEl) headerEl.appendChild(badgeEl);

      if (cardEval.analysis) {
        const noteEl = document.createElement("div");
        noteEl.className = "ai-card-note";
        noteEl.innerHTML = `<strong>Gemini Tactical Fit:</strong> ${escapeHtml(cardEval.analysis)}`;
        const auditBox = cardEl.querySelector(".role-audit-box");
        if (auditBox && auditBox.parentNode) {
          auditBox.parentNode.insertBefore(noteEl, auditBox.nextSibling);
        } else {
          cardEl.appendChild(noteEl);
        }
      }
    } else if (isTopChoice) {
      const badgeEl = document.createElement("span");
      badgeEl.className = "ai-tier-badge tier-top-pick";
      badgeEl.textContent = "Top Pick";
      const headerEl = cardEl.querySelector(".card-header");
      if (headerEl) headerEl.appendChild(badgeEl);
    }
  });

  // 3. Populate Refinement Suggestions
  renderChatSuggestions(rec, lastEvaluatedCards);
}

// --- INTERACTIVE REFINING CHAT CONTROLLER ---
function setupAIChat() {
  const input = document.getElementById("aiChatInput");
  const btnSend = document.getElementById("btnSendAIChat");

  if (btnSend) {
    btnSend.addEventListener("click", sendAIChatMessage);
  }

  if (input) {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        sendAIChatMessage();
      }
    });
  }
}

function renderChatSuggestions(rec, cards) {
  const container = document.getElementById("aiChatSuggestions");
  if (!container) return;
  container.innerHTML = "";

  const suggestions = [];
  const recommended = (rec && rec.recommended_card) || "";

  // Suggest comparing against other offered cards
  (cards || []).forEach(c => {
    if (c.trim().toLowerCase() !== recommended.toLowerCase()) {
      suggestions.push(`What if I take ${c.trim()} instead?`);
    }
  });

  suggestions.push("How does this choice prepare for the Act boss?");
  suggestions.push("What should my next campfire upgrade be?");
  suggestions.push("Which combat encounters should I be most careful of?");

  suggestions.slice(0, 4).forEach(promptText => {
    const chip = document.createElement("button");
    chip.className = "ai-suggestion-chip";
    chip.textContent = promptText;
    chip.addEventListener("click", () => {
      const input = document.getElementById("aiChatInput");
      if (input) {
        input.value = promptText;
        sendAIChatMessage();
      }
    });
    container.appendChild(chip);
  });
}

async function sendAIChatMessage() {
  const input = document.getElementById("aiChatInput");
  const btnSend = document.getElementById("btnSendAIChat");
  const messagesContainer = document.getElementById("aiChatMessages");
  if (!input || !messagesContainer) return;

  const text = input.value.trim();
  if (!text) return;

  input.value = "";

  // Render User Bubble
  const userBubble = document.createElement("div");
  userBubble.className = "ai-message-bubble user";
  userBubble.textContent = text;
  messagesContainer.appendChild(userBubble);

  // Render Loading Indicator
  const loadingBubble = document.createElement("div");
  loadingBubble.className = "ai-message-bubble ai loading";
  loadingBubble.innerHTML = `<span>🧠</span> Gemini is analyzing your question...`;
  messagesContainer.appendChild(loadingBubble);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;

  if (btnSend) {
    btnSend.disabled = true;
  }

  try {
    const res = await fetch("/api/ai_chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        history: currentChatHistory,
        cards: lastEvaluatedCards,
        initial_recommendation: lastAIRec,
      }),
    });

    const data = await res.json();
    loadingBubble.remove();

    if (data.success && data.reply) {
      const aiBubble = document.createElement("div");
      aiBubble.className = "ai-message-bubble ai";
      aiBubble.innerHTML = formatMarkdown(data.reply);
      messagesContainer.appendChild(aiBubble);

      currentChatHistory.push({ role: "user", content: text });
      currentChatHistory.push({ role: "model", content: data.reply });
    } else {
      const errBubble = document.createElement("div");
      errBubble.className = "ai-message-bubble ai";
      errBubble.style.borderColor = "#ef4444";
      errBubble.innerHTML = `<strong>Error:</strong> ${escapeHtml(data.error || "Failed to get advice from Gemini.")}`;
      messagesContainer.appendChild(errBubble);
    }
  } catch (err) {
    loadingBubble.remove();
    const errBubble = document.createElement("div");
    errBubble.className = "ai-message-bubble ai";
    errBubble.style.borderColor = "#ef4444";
    errBubble.innerHTML = `<strong>Network Error:</strong> ${escapeHtml(err.message)}`;
    messagesContainer.appendChild(errBubble);
  } finally {
    if (btnSend) {
      btnSend.disabled = false;
    }
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }
}

function formatMarkdown(text) {
  if (!text) return "";
  let html = escapeHtml(text);
  // Bold **text**
  html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  // Italic *text*
  html = html.replace(/\*(.*?)\*/g, "<em>$1</em>");
  // Bullet lists (- item)
  html = html.replace(/(?:^|\n)-\s+(.*?)(?=\n|$)/g, "<li>$1</li>");
  html = html.replace(/(<li>.*<\/li>)/s, "<ul>$1</ul>");
  // Paragraphs
  html = html.replace(/\n\n+/g, "</p><p>");
  html = `<p>${html}</p>`;
  html = html.replace(/<p>\s*<\/p>/g, "");
  return html;
}

// Settings Modal Controller
function setupSettingsModal() {
  const btnSettings = document.getElementById("btnSettings");
  const modal = document.getElementById("settingsModal");
  const btnClose = document.getElementById("btnCloseModal");
  const btnCancel = document.getElementById("btnCancelSettings");
  const btnSave = document.getElementById("btnSaveSettings");
  const btnToggleVis = document.getElementById("btnToggleKeyVis");
  const inputKey = document.getElementById("inputApiKey");

  if (btnSettings) btnSettings.addEventListener("click", openSettingsModal);
  if (btnClose) btnClose.addEventListener("click", closeSettingsModal);
  if (btnCancel) btnCancel.addEventListener("click", closeSettingsModal);
  if (btnSave) btnSave.addEventListener("click", saveSettings);

  if (btnToggleVis && inputKey) {
    btnToggleVis.addEventListener("click", () => {
      if (inputKey.type === "password") {
        inputKey.type = "text";
        btnToggleVis.textContent = "Hide";
      } else {
        inputKey.type = "password";
        btnToggleVis.textContent = "Show";
      }
    });
  }

  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) closeSettingsModal();
    });
  }
}

async function openSettingsModal() {
  const modal = document.getElementById("settingsModal");
  const feedback = document.getElementById("settingsFeedback");
  if (feedback) feedback.className = "settings-feedback hidden";

  try {
    const res = await fetch("/api/config");
    const data = await res.json();

    const inputKey = document.getElementById("inputApiKey");
    const keyHint = document.getElementById("keyStatusHint");
    const selectModel = document.getElementById("selectModel");
    const chkSearch = document.getElementById("chkSearchGrounding");

    if (data.gemini_api_key_configured) {
      if (keyHint) keyHint.innerHTML = `✅ Key configured (${escapeHtml(data.masked_key)}). Enter new key to replace.`;
      if (inputKey) inputKey.placeholder = `Configured (${data.masked_key})`;
    } else {
      if (keyHint) keyHint.innerHTML = `⚠️ No key configured. Paste your Google Gemini API key below.`;
      if (inputKey) inputKey.placeholder = "AIza...";
    }

    if (selectModel && data.gemini_model) selectModel.value = data.gemini_model;
    if (chkSearch) chkSearch.checked = data.enable_search_grounding !== false;

  } catch (err) {
    console.error("Error loading config:", err);
  }

  if (modal) modal.classList.remove("hidden");
}

function closeSettingsModal() {
  const modal = document.getElementById("settingsModal");
  if (modal) modal.classList.add("hidden");
}

async function saveSettings() {
  const inputKey = document.getElementById("inputApiKey");
  const selectModel = document.getElementById("selectModel");
  const chkSearch = document.getElementById("chkSearchGrounding");
  const feedback = document.getElementById("settingsFeedback");

  const updates = {};
  if (inputKey && inputKey.value.trim()) {
    updates.gemini_api_key = inputKey.value.trim();
  }
  if (selectModel) {
    updates.gemini_model = selectModel.value;
  }
  if (chkSearch) {
    updates.enable_search_grounding = chkSearch.checked;
  }

  try {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    const data = await res.json();

    if (data.success) {
      isApiKeyConfigured = !!data.config.gemini_api_key_configured;
      if (feedback) {
        feedback.className = "settings-feedback success";
        feedback.textContent = "✅ Settings saved successfully!";
        feedback.classList.remove("hidden");
      }
      setTimeout(() => {
        closeSettingsModal();
        if (inputKey) inputKey.value = "";
      }, 1000);
    } else {
      if (feedback) {
        feedback.className = "settings-feedback error";
        feedback.textContent = `❌ ${data.error || "Failed to save settings."}`;
        feedback.classList.remove("hidden");
      }
    }
  } catch (err) {
    if (feedback) {
      feedback.className = "settings-feedback error";
      feedback.textContent = `❌ Network error saving settings: ${err.message}`;
      feedback.classList.remove("hidden");
    }
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

    // Map tactical fit to badge class
    let fitClass = "addition";
    if (opt.tactical_fit === "Fills Critical Gap") fitClass = "critical";
    else if (opt.tactical_fit === "Strong Synergy") fitClass = "synergy";
    else if (opt.tactical_fit === "Redundant Role") fitClass = "redundant";
    else if (opt.tactical_fit === "Dilution Risk") fitClass = "dilution";

    // Role audit box
    const audit = opt.role_audit || {};
    const auditCountClass = audit.is_critical ? "role-audit-count critical" : "role-audit-count";
    const auditHtml = `
      <div class="role-audit-box">
        <div class="role-audit-header">
          <span>${escapeHtml(opt.primary_role_label || "Role Audit")}</span>
          <span class="${auditCountClass}">${audit.current_count} in deck (${audit.deck_percentage}%)</span>
        </div>
        <div class="role-audit-text">${escapeHtml(audit.gap_description || "")}</div>
      </div>
    `;

    // Combos HTML
    let combosHtml = "";
    const cardCombos = opt.card_combos || [];
    const relicCombos = opt.relic_combos || [];
    if (cardCombos.length > 0 || relicCombos.length > 0) {
      const cItems = cardCombos.map(combo =>
        `<div class="combo-chip"><span class="combo-tag card">CARD</span><strong>${escapeHtml(combo.partner)}</strong>: ${escapeHtml(combo.explanation)}</div>`
      ).join("");
      const rItems = relicCombos.map(rcombo =>
        `<div class="combo-chip"><span class="combo-tag relic">RELIC</span><strong>${escapeHtml(rcombo.relic)}</strong>: ${escapeHtml(rcombo.explanation)}</div>`
      ).join("");

      combosHtml = `
        <div class="combos-container">
          <div class="combos-header"><span>⚡</span> Synergies with Deck & Relics</div>
          ${cItems}
          ${rItems}
        </div>
      `;
    }

    const prosHtml = (opt.pros || []).map(p => `<div class="pro-item"><span>+</span><span>${escapeHtml(p)}</span></div>`).join("");
    const consHtml = (opt.cons || []).map(con => `<div class="con-item"><span>-</span><span>${escapeHtml(con)}</span></div>`).join("");

    let pStatHtml = "";
    if (opt.personal_stats) {
      const ps = opt.personal_stats;
      pStatHtml = `<div class="personal-stat-tag">📊 Your History: ${escapeHtml(ps.highlight)} | Picked ${ps.pick_rate}%</div>`;
    }

    cardEl.innerHTML = `
      <div class="ranked-card-header">
        <div>
          <span class="ranked-card-title">${escapeHtml(c.name)}</span><br>
          <span class="card-type-tag type-${c.card_type}">${escapeHtml(c.card_type || "Card")} (${escapeHtml(c.character || "all")})</span>
        </div>
        <div class="tactical-badge badge-${fitClass}">${escapeHtml(opt.tactical_fit)}</div>
      </div>
      <div class="card-description-box">${escapeHtml(c.description || "No text")}</div>
      ${auditHtml}
      ${combosHtml}
      <div class="reasoning-list">
        ${prosHtml}
        ${consHtml}
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
