const APP_NAME = "ritual_detective";
const USER_ID = "detective_player";

let currentSessionId = null;

const adkUrlInput = document.getElementById("adkUrlInput");
const newSessionBtn = document.getElementById("newSessionBtn");
const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const chatStream = document.getElementById("chatStream");
const hypothesisForm = document.getElementById("hypothesisForm");
const hypothesisInput = document.getElementById("hypothesisInput");
const submitBtn = document.getElementById("submitBtn");
const followupBar = document.getElementById("followupBar");
const followupButtons = document.getElementById("followupButtons");

// Notebook sidebar elements
const sessionIdBadge = document.getElementById("sessionIdBadge");
const metricTurn = document.getElementById("metricTurn");
const metricHypotheses = document.getElementById("metricHypotheses");
const metricSources = document.getElementById("metricSources");
const activeLeadBox = document.getElementById("activeLeadBox");
const historyList = document.getElementById("historyList");
const searchTraceList = document.getElementById("searchTraceList");
const sourcesList = document.getElementById("sourcesList");

function getBaseUrl() {
  return adkUrlInput.value.trim().replace(/\/+$/, "");
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderMarkdown(md) {
  let html = escapeHtml(md);

  // Convert Markdown links [title](url)
  html = html.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">🔗 $1</a>'
  );

  // Inline code and bold/italic
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");

  const lines = html.split("\n");
  const out = [];
  let inList = false;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      if (inList) {
        out.push("</ul>");
        inList = false;
      }
      continue;
    }
    if (line === "---") {
      if (inList) {
        out.push("</ul>");
        inList = false;
      }
      out.push("<hr />");
      continue;
    }
    if (line.startsWith("### ")) {
      if (inList) {
        out.push("</ul>");
        inList = false;
      }
      out.push(`<h3>${line.slice(4)}</h3>`);
      continue;
    }
    if (line.startsWith("#### ")) {
      if (inList) {
        out.push("</ul>");
        inList = false;
      }
      out.push(`<h4>${line.slice(5)}</h4>`);
      continue;
    }
    if (/^(\*|-|\d+\.)\s+/.test(line)) {
      if (!inList) {
        out.push("<ul>");
        inList = true;
      }
      out.push(`<li>${line.replace(/^(\*|-|\d+\.)\s+/, "")}</li>`);
      continue;
    }
    if (inList) {
      out.push("</ul>");
      inList = false;
    }
    out.push(`<p>${line}</p>`);
  }
  if (inList) out.push("</ul>");
  return out.join("\n");
}

async function createAdkSession() {
  const baseUrl = getBaseUrl();
  try {
    const res = await fetch(
      `${baseUrl}/apps/${APP_NAME}/users/${USER_ID}/sessions`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      }
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    currentSessionId = data.id;
    sessionIdBadge.textContent = `Session: ${currentSessionId.slice(0, 8)}`;
    statusDot.className = "status-dot online";
    statusText.textContent = `Connected to ADK (${APP_NAME})`;
    updateNotebookSidebar(data.state || {});
    return currentSessionId;
  } catch (err) {
    statusDot.className = "status-dot offline";
    statusText.textContent = `ADK server unreachable at ${baseUrl}`;
    return null;
  }
}

function updateNotebookSidebar(state) {
  const turnCount = state.turn_count || 0;
  const history = state.hypothesis_history || [];
  const searchTrace = state.search_trace || [];
  const sources = state.evidence_sources || [];
  const followUps = state.suggested_follow_ups || [];

  metricTurn.textContent = turnCount;
  metricHypotheses.textContent = Math.max(history.length, turnCount);
  metricSources.textContent = sources.length;

  if (state.current_hypothesis) {
    activeLeadBox.innerHTML = `<span class="turn-pill">Turn ${turnCount}</span> ${escapeHtml(
      state.current_hypothesis
    )}`;
  } else {
    activeLeadBox.textContent = "No hypothesis submitted yet.";
  }

  if (history.length > 0) {
    historyList.innerHTML = history
      .map(
        (h) =>
          `<li><span class="turn-pill">Turn ${h.turn}</span> <strong>${escapeHtml(
            h.mode
          )}:</strong> ${escapeHtml(h.resolved_hypothesis)}</li>`
      )
      .join("");
  } else {
    historyList.innerHTML =
      '<li class="notebook-empty">Turns in this session will appear here.</li>';
  }

  if (searchTrace.length > 0) {
    searchTraceList.innerHTML = searchTrace
      .map(
        (st) =>
          `<li><span class="turn-pill">Turn ${st.turn}</span> ${st.queries
            .map((q) => `<code>${escapeHtml(q)}</code>`)
            .join(", ")}</li>`
      )
      .join("");
  } else {
    searchTraceList.innerHTML =
      '<li class="notebook-empty">Live search queries executed by Gemini will appear here.</li>';
  }

  if (sources.length > 0) {
    sourcesList.innerHTML = sources
      .map(
        (s, i) =>
          `<li><span class="turn-pill">T${s.turn}</span> <a href="${escapeHtml(
            s.url
          )}" target="_blank" rel="noopener noreferrer">[${i + 1}] ${escapeHtml(
            s.title
          )}</a></li>`
      )
      .join("");
  } else {
    sourcesList.innerHTML =
      '<li class="notebook-empty">Clickable source links from grounding metadata will appear here.</li>';
  }

  // Render clickable follow-up buttons for Turn 2+
  if (followUps.length > 0) {
    followupBar.classList.remove("hidden");
    followupButtons.innerHTML = followUps
      .map(
        (fu, idx) =>
          `<button type="button" class="followup-btn" data-choice="${idx + 1}">
            <span class="lead-num">Lead #${idx + 1}</span>
            <span>${escapeHtml(fu)}</span>
          </button>`
      )
      .join("");

    followupButtons.querySelectorAll(".followup-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const choice = btn.getAttribute("data-choice");
        sendInvestigationTurn(choice, `Selected Follow-Up Lead #${choice}: ${btn.innerText}`);
      });
    });
  } else {
    followupBar.classList.add("hidden");
  }
}

async function sendInvestigationTurn(playerInput, displayLabel = null) {
  if (!playerInput.trim()) return;
  if (!currentSessionId) {
    await createAdkSession();
  }
  const welcome = chatStream.querySelector(".welcome-card");
  if (welcome) welcome.remove();

  // Append user bubble
  const userDiv = document.createElement("div");
  userDiv.className = "msg-user";
  userDiv.innerHTML = `<div class="msg-meta">🕵️ Player Hypothesis / Lead</div><div>${escapeHtml(
    displayLabel || playerInput
  )}</div>`;
  chatStream.appendChild(userDiv);

  // Append loading bubble
  const loadingDiv = document.createElement("div");
  loadingDiv.className = "msg-agent loading-bubble";
  loadingDiv.innerHTML = `<div class="spinner"></div><span>The Ritual Detective is searching historical &amp; anthropological sources via Google ADK...</span>`;
  chatStream.appendChild(loadingDiv);
  chatStream.scrollTop = chatStream.scrollHeight;

  submitBtn.disabled = true;
  hypothesisInput.value = "";

  const baseUrl = getBaseUrl();
  try {
    const runRes = await fetch(`${baseUrl}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        app_name: APP_NAME,
        user_id: USER_ID,
        session_id: currentSessionId,
        new_message: {
          role: "user",
          parts: [{ text: playerInput }],
        },
      }),
    });

    if (!runRes.ok) throw new Error(`ADK /run returned HTTP ${runRes.status}`);
    const events = await runRes.json();

    let agentText = "";
    for (const ev of events) {
      if (ev.content && ev.content.parts) {
        for (const p of ev.content.parts) {
          if (p.text) agentText = p.text;
        }
      }
    }

    loadingDiv.className = "msg-agent";
    loadingDiv.innerHTML = renderMarkdown(
      agentText || "Investigation complete—inspect the Case Notebook on the right."
    );

    // Fetch updated session state from ADK
    const sessRes = await fetch(
      `${baseUrl}/apps/${APP_NAME}/users/${USER_ID}/sessions/${currentSessionId}`
    );
    if (sessRes.ok) {
      const sessData = await sessRes.json();
      updateNotebookSidebar(sessData.state || {});
    }
  } catch (err) {
    loadingDiv.className = "msg-agent";
    loadingDiv.innerHTML = `<p>⚠️ <strong>Could not reach ADK server at <code>${escapeHtml(
      baseUrl
    )}</code></strong> (${escapeHtml(
      err.message
    )}). Ensure <code>adk web --port 8000 --allow_origins "*"</code> is running.</p>`;
  } finally {
    submitBtn.disabled = false;
    chatStream.scrollTop = chatStream.scrollHeight;
  }
}

// Event listeners
hypothesisForm.addEventListener("submit", (e) => {
  e.preventDefault();
  sendInvestigationTurn(hypothesisInput.value);
});

newSessionBtn.addEventListener("click", async () => {
  chatStream.innerHTML = "";
  followupBar.classList.add("hidden");
  await createAdkSession();
});

document.querySelectorAll(".starter-card").forEach((card) => {
  card.addEventListener("click", () => {
    const prompt = card.getAttribute("data-prompt");
    sendInvestigationTurn(prompt);
  });
});

// Initialize session on page load
createAdkSession();
