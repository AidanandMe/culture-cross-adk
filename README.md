# Culture Cross: The Ritual Detective 🕵️‍♀️🕯️🎃

**Culture Cross: The Ritual Detective** is a playful, evidence-grounded educational application built for the **Google AI DevCamp Agentic AI Hackathon**. It investigates cultural similarities, differences, and documented historical transmission between traditions—starting with **Halloween** and Mexico's **Día de los Muertos**.

Rather than treating cultural overlap as simple equivalence, the agent acts as a historical and anthropological investigator: formulating targeted web searches, separating documented historical transmission from parallel motifs and misconceptions, preserving source provenance, and maintaining a multi-turn **Cultural Investigation Notebook** in **Google ADK session state**.

---

## 🛠️ Technical Stack

- **Agent Framework**: [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/) (`google-adk`)
- **LLM**: Google **Gemini** (`gemini-3-flash-preview` via `google-genai`)
- **Grounding & Tool Calling**: Built-in **Google Search Grounding** (`google.adk.tools.google_search` / `GoogleSearchTool`) retrieving live web search queries (`web_search_queries`) and grounding source chunks (`grounding_chunks` & `grounding_supports`)
- **Stateful Multi-Turn Memory**: **ADK Session State** (`CallbackContext.state` via `before_agent_callback` and `after_model_callback`) with SQLite persistence in `adk web` (`SqliteSessionService`) and `InMemoryRunner` support for CLI/automated tests
- **Language & Runtime**: Python 3.11+ (`python-dotenv`, `httpx`)

---

## 🏗️ Google ADK Architecture

```
culture-cross-adk/
├── ritual_detective/
│   ├── __init__.py          # ADK package discovery & .env loader
│   ├── agent.py             # Root ADK Agent (`root_agent`), Gemini model, Google Search tool & instructions
│   └── notebook.py          # ADK `before_agent_callback` & `after_model_callback` managing Session State Notebook
├── notebook_cli.py          # Interactive terminal Cultural Investigation Notebook (multi-turn CLI)
├── verify_agent.py          # Single-turn live ADK + Google Search grounding verification script
├── verify_two_turn_notebook.py # Automated two-turn session-state & provenance verification suite
├── run_web.bat              # Windows helper script to launch ADK Web on port 8000
├── .env.example             # Placeholder template for Gemini API configuration
└── requirements.txt         # Locked Python dependencies
```

### Key Architectural Components

1. **Root Agent ([`ritual_detective/agent.py`](ritual_detective/agent.py))**
   - Defines `root_agent = Agent(...)` using the official `google.adk.agents.Agent` class and `google_search` from `google.adk.tools`.
   - Enforces a structured **4-Tier Evidence Classification**:
     1. **Documented Historical Facts & Transmission** (attested historical roots, dates, and colonial/liturgical contact)
     2. **Cultural Similarities (Parallel Motifs)** (shared themes that do not by themselves prove direct causation)
     3. **Scholarly Interpretations** (academic models and ongoing debates)
     4. **Unsupported Claims & Uncertainties** (common myths debunked and gaps in primary historical records)
   - Uses ADK's native `{notebook_context_prompt}` state interpolation to inject the active session's investigation history into the system instruction on every turn.

2. **Stateful Cultural Investigation Notebook ([`ritual_detective/notebook.py`](ritual_detective/notebook.py))**
   - **`before_investigation_turn` (`before_agent_callback`)**:
     - Synchronizes with `callback_context.session.events` and updates `session.state` (`turn_count`, `active_mode`, `current_hypothesis`, `hypothesis_history`, `search_trace`, `evidence_sources`, `suggested_follow_ups`).
     - Resolves shorthand player selections (`1`, `2`, `3`) on Turn 2+ directly against `session.state["suggested_follow_ups"]`.
   - **`after_investigation_model` (`after_model_callback`)**:
     - Extracts live Google Search queries (`grounding_metadata.web_search_queries`) and retrieved web sources (`grounding_metadata.grounding_chunks`) into `session.state`.
     - Resolves inline references and `grounding_supports` segments to clickable source links and appends a deterministic **Session Investigation Notebook & Provenance Trace** footer calculated directly from ADK session state.

---

## 🚀 Setup & Installation

### 1. Clone the Repository & Create a Virtual Environment

```powershell
git clone https://github.com/AidanandMe/culture-cross-adk.git
cd culture-cross-adk

python -m venv .venv
```

### 2. Install Dependencies

**Windows (PowerShell):**
```powershell
.\.venv\Scripts\pip.exe install -r requirements.txt
```

**macOS / Linux:**
```bash
./.venv/bin/pip install -r requirements.txt
```

### 3. Configure Your Gemini API Key

Copy `.env.example` to `.env` and add your Google AI Studio / Gemini API key:

```powershell
Copy-Item .env.example .env
```

Edit `.env`:
```env
GOOGLE_GENAI_USE_VERTEXAI=FALSE
GOOGLE_API_KEY=your_google_ai_studio_api_key_here
GEMINI_MODEL=gemini-3-flash-preview
```

---

## 🧪 Running the Application

### Option 1: Official Google ADK Web UI (Recommended for Demo)

Run from the project root in PowerShell:
```powershell
.\.venv\Scripts\adk.exe web --port 8000
```
*(Or on Windows, double-click / run `.\run_web.bat`.)*

1. Open **http://127.0.0.1:8000** in your browser.
2. Select **`ritual_detective`** from the top-left agent dropdown.
3. **Turn 1**: Submit a cultural hypothesis, e.g.:
   > *"Did Halloween and Mexico's Día de los Muertos originate from the same ancient festival?"*
4. **Turn 2**: Reply with **`1`**, **`2`**, or **`3`** to launch one of the suggested follow-up investigations, or enter a revised hypothesis (e.g., *"So, did they merge in some way because of the cultural contact after the so-called 'discovery of the Americas'?"*).
5. Click the **State** and **Trace / Events** tabs in the ADK Web sidebar to inspect the live `session.state` notebook (`turn_count`, `hypothesis_history`, `search_trace`, `evidence_sources`, `suggested_follow_ups`) and grounding metadata.

### Option 2: Interactive Terminal Investigation Notebook

```powershell
.\.venv\Scripts\python.exe notebook_cli.py
```
- Type a hypothesis to start investigating.
- Type `1`, `2`, or `3` to pursue a suggested follow-up lead.
- Type `state` at any time to inspect the full JSON contents of `session.state`.

### Option 3: Automated Two-Turn Workflow Verification

```powershell
.\.venv\Scripts\python.exe verify_two_turn_notebook.py
```
Runs a complete two-turn investigation within a single ADK session and verifies session state persistence, Google Search grounding trace capture, and clickable source provenance.
