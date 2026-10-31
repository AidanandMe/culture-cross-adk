import re
from typing import Any, Optional
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse
from google.genai import types


def _extract_user_text(user_content: Optional[types.Content]) -> str:
    """Extracts plain text from a user message Content object, ignoring function responses."""
    if not user_content or not user_content.parts:
        return ""
    if any(getattr(p, "function_response", None) for p in user_content.parts):
        return ""
    texts = [p.text.strip() for p in user_content.parts if getattr(p, "text", None)]
    return " ".join(t for t in texts if t).strip()


def _resolve_followup_choice(raw_input: str, suggested_follow_ups: list[str]) -> tuple[str, bool]:
    """Resolves a numeric or path selection (e.g. '1', '2', 'Path 1') against suggested_follow_ups."""
    cleaned = raw_input.strip()
    if not suggested_follow_ups:
        return cleaned, False

    m_num = re.match(
        r"^(?:option|path|follow[- ]?up|lead|#)?\s*([1-9])\b[\s:.-]*(.*)$",
        cleaned,
        re.IGNORECASE,
    )
    if m_num:
        idx = int(m_num.group(1)) - 1
        extra = m_num.group(2).strip()
        if 0 <= idx < len(suggested_follow_ups):
            chosen = suggested_follow_ups[idx]
            if extra:
                return (
                    f"Follow-up Investigation [{idx + 1}]: {chosen} (Player refinement: {extra})",
                    True,
                )
            return f"Follow-up Investigation [{idx + 1}]: {chosen}", True

    m_letter = re.match(r"^(?:path|option)?\s*([ABC])\b[\s:.-]*(.*)$", cleaned, re.IGNORECASE)
    if m_letter and len(cleaned) <= 12:
        idx = ord(m_letter.group(1).upper()) - ord("A")
        if 0 <= idx < len(suggested_follow_ups):
            return f"Follow-up Investigation [{idx + 1}]: {suggested_follow_ups[idx]}", True

    return cleaned, False


def _parse_follow_ups_from_text(response_text: str) -> list[str]:
    """Extracts the 3 numbered follow-up investigation options from the agent's report."""
    followup_section = response_text
    section_match = re.search(
        r"(?:Follow-Up|Next Investigation|Suggested Follow-Up|Proposed Follow-Up).*?$",
        response_text,
        re.IGNORECASE | re.DOTALL,
    )
    if section_match:
        followup_section = section_match.group(0)

    items: list[str] = []
    for line in followup_section.splitlines():
        line_clean = line.strip()
        m = re.match(r"^(?:[1-3][\.\)]|\-\s*\[[1-3]\])\s*(.+)$", line_clean)
        if m:
            candidate = re.sub(r"\*+", "", m.group(1)).strip()
            if candidate and len(candidate) > 10:
                items.append(candidate)

    return items[:3]


def _sync_state_from_session_events(callback_context: CallbackContext) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Inspects actual ADK session.events to ensure turn history, queries, and sources are never lost.

    Even if a session was started before a server restart, this reconstructs prior user turns
    and prior grounding metadata directly from `callback_context.session.events`.
    """
    session = getattr(callback_context, "session", None)
    events = getattr(session, "events", None) or []

    user_messages: list[str] = []
    event_queries_by_turn: list[dict[str, Any]] = []
    event_sources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    current_turn_idx = 0
    for ev in events:
        author = getattr(ev, "author", "")
        content = getattr(ev, "content", None)
        if author == "user" and content:
            utext = _extract_user_text(content)
            if utext:
                user_messages.append(utext)
                current_turn_idx = len(user_messages)

        gm = getattr(ev, "grounding_metadata", None)
        if gm:
            t_idx = max(1, current_turn_idx)
            queries = [q for q in (getattr(gm, "web_search_queries", None) or []) if q]
            if queries:
                event_queries_by_turn.append(
                    {
                        "turn": t_idx,
                        "hypothesis": user_messages[t_idx - 1] if t_idx <= len(user_messages) else "",
                        "queries": queries,
                    }
                )
            for chunk in getattr(gm, "grounding_chunks", None) or []:
                web = getattr(chunk, "web", None)
                uri = getattr(web, "uri", None) if web else None
                title = (getattr(web, "title", None) if web else None) or "Retrieved Web Source"
                if uri and uri not in seen_urls:
                    seen_urls.add(uri)
                    event_sources.append(
                        {
                            "turn": t_idx,
                            "title": title,
                            "url": uri,
                        }
                    )

    return user_messages, event_queries_by_turn, event_sources


def _build_notebook_context(state: Any) -> str:
    """Builds a concise summary of the ADK session state notebook for the agent instruction."""
    turn_count = state.get("turn_count", 1)
    active_mode = state.get("active_mode", "initial_hypothesis")
    current_hyp = state.get("current_hypothesis", "")
    history = state.get("hypothesis_history", [])
    sources = state.get("evidence_sources", [])
    search_trace = state.get("search_trace", [])

    lines = [
        f"- **Current Session Turn**: {turn_count}",
        f"- **Turn Mode**: {active_mode}",
        f"- **Active Hypothesis / Lead to Investigate Now**: {current_hyp}",
    ]

    if len(history) > 1:
        prior = [f"Turn {h['turn']}: {h['resolved_hypothesis']}" for h in history[:-1]]
        lines.append("- **Prior Session Hypotheses**: " + " | ".join(prior))

    if search_trace:
        prior_queries = [q for entry in search_trace for q in entry.get("queries", [])]
        if prior_queries:
            lines.append(
                f"- **Prior Google Searches Executed in This Session ({len(prior_queries)})**: "
                + ", ".join(f'"{q}"' for q in prior_queries[-6:])
            )

    if sources:
        lines.append(
            f"- **Cumulative Retrieved Grounding Sources in Session Notebook**: {len(sources)} sources recorded."
        )

    return "\n".join(lines)


def before_investigation_turn(callback_context: CallbackContext) -> Optional[types.Content]:
    """ADK before_agent_callback: Initializes and updates the Cultural Investigation Notebook in session state."""
    state = callback_context.state

    if "notebook_initialized" not in state:
        state["notebook_initialized"] = True
        state["notebook_title"] = "Culture Cross: The Ritual Detective — Investigation Notebook"
        state["turn_count"] = 0
        state["current_hypothesis"] = ""
        state["active_mode"] = "initial_hypothesis"
        state["hypothesis_history"] = []
        state["search_trace"] = []
        state["evidence_sources"] = []
        state["suggested_follow_ups"] = []
        state["investigation_reports"] = []

    # Reconcile with actual session.events so pre-existing turns in the session are never missed
    session_user_msgs, session_queries, session_sources = _sync_state_from_session_events(
        callback_context
    )
    raw_user_text = _extract_user_text(callback_context.user_content)

    # Ensure all prior user messages from session.events are represented in hypothesis_history
    history: list[dict[str, Any]] = list(state.get("hypothesis_history", []))
    prior_msgs = session_user_msgs[:-1] if (session_user_msgs and session_user_msgs[-1] == raw_user_text) else session_user_msgs
    if len(history) < len(prior_msgs):
        rebuilt_history: list[dict[str, Any]] = []
        for idx, msg_text in enumerate(prior_msgs, 1):
            existing = next((h for h in history if h.get("turn") == idx), None)
            if existing:
                rebuilt_history.append(existing)
            else:
                rebuilt_history.append(
                    {
                        "turn": idx,
                        "mode": "initial_hypothesis" if idx == 1 else "revised_hypothesis",
                        "player_input": msg_text,
                        "resolved_hypothesis": msg_text,
                    }
                )
        history = rebuilt_history

    turn_num = len(history) + 1
    state["turn_count"] = turn_num

    prior_follow_ups = list(state.get("suggested_follow_ups", []))
    resolved_hypothesis, is_followup = _resolve_followup_choice(raw_user_text, prior_follow_ups)

    if turn_num == 1:
        mode = "initial_hypothesis"
    elif is_followup:
        mode = "selected_follow_up_investigation"
    else:
        mode = "revised_hypothesis"

    state["active_mode"] = mode
    state["current_hypothesis"] = resolved_hypothesis

    history.append(
        {
            "turn": turn_num,
            "mode": mode,
            "player_input": raw_user_text,
            "resolved_hypothesis": resolved_hypothesis,
        }
    )
    state["hypothesis_history"] = history

    # Merge any grounded sources/queries from earlier events in this session
    if session_sources:
        existing_sources = list(state.get("evidence_sources", []))
        seen_urls = {s.get("url") for s in existing_sources}
        for src in session_sources:
            if src["url"] not in seen_urls:
                existing_sources.append(src)
                seen_urls.add(src["url"])
        state["evidence_sources"] = existing_sources

    if session_queries and not state.get("search_trace"):
        state["search_trace"] = session_queries

    state["notebook_context_prompt"] = _build_notebook_context(state)
    return None


def _inject_clickable_citations_and_clean_text(
    text: str,
    turn_sources: list[dict[str, Any]],
    grounding_metadata: Optional[types.GroundingMetadata],
) -> str:
    """Resolves inline bracket citations to real clickable URLs, injects grounding support links, and removes stray formatting artifacts."""
    # 1. Strip any echoed footer if the model generated one
    cleaned = re.sub(
        r"\n*---\s*\n*### 📓 Session Investigation Notebook & Provenance Trace.*",
        "",
        text,
        flags=re.DOTALL,
    ).rstrip()

    # 2. If grounding_supports is present, attach clickable [Title](URL) citations to grounded segments
    #    before line-level cleanup, or map inline bracket citations [1], [1.2.5] to real URLs.
    def _replace_bracket_ref(match: re.Match) -> str:
        inner = match.group(1).strip()
        # Split comma-separated refs like [1, 2] or [1.2.1, 1.2.4]
        tokens = [t.strip() for t in inner.split(",") if t.strip()]
        rendered_links: list[str] = []
        for tok in tokens:
            if tok.isdigit() and turn_sources:
                idx = int(tok) - 1
                if 0 <= idx < len(turn_sources):
                    src = turn_sources[idx]
                    rendered_links.append(f"[{src['title']}]({src['url']})")
            elif re.match(r"^\d+(?:\.\d+)+$", tok):
                # Multi-decimal pseudo-citation like 1.2.5: map last number to turn_sources if available, else strip
                last_num = int(tok.split(".")[-1])
                if turn_sources and 1 <= last_num <= len(turn_sources):
                    src = turn_sources[last_num - 1]
                    rendered_links.append(f"[{src['title']}]({src['url']})")
        if rendered_links:
            # Deduplicate while preserving order
            dedup: list[str] = []
            for lnk in rendered_links:
                if lnk not in dedup:
                    dedup.append(lnk)
            return " (" + ", ".join(dedup) + ")"
        # Strip unresolvable numeric/decimal citation artifacts like [1.2.5]
        return ""

    # Match bracketed numeric or dotted-numeric refs like [1], [1, 2], [1.2.5], [1.2.1, 1.2.4]
    # that are NOT followed by '(' (so existing markdown links [text](url) are untouched)
    cleaned = re.sub(
        r"\s*\[(\d+(?:\.\d+)*(?:\s*,\s*\d+(?:\.\d+)*)*)\](?!\()",
        _replace_bracket_ref,
        cleaned,
    )

    # 3. Also attach clickable source links to grounded bullet points using grounding_supports
    #    when the bullet does not already contain a clickable http link
    if grounding_metadata and getattr(grounding_metadata, "grounding_supports", None) and turn_sources:
        lines = cleaned.splitlines()
        for idx, line in enumerate(lines):
            # Only enrich bullet lines in the Evidence section (not headers or numbered follow-ups)
            stripped = line.strip()
            if not (stripped.startswith("* ") or stripped.startswith("- ")):
                continue
            if "](http" in line:
                continue
            matched_links: list[str] = []
            for sup in grounding_metadata.grounding_supports:
                seg = getattr(sup, "segment", None)
                seg_text = (getattr(seg, "text", None) or "").strip()
                chunk_indices = getattr(sup, "grounding_chunk_indices", None) or []
                if seg_text and len(seg_text) > 20 and seg_text[:35] in line:
                    for c_idx in chunk_indices:
                        if 0 <= c_idx < len(turn_sources):
                            src = turn_sources[c_idx]
                            lnk = f"[{src['title']}]({src['url']})"
                            if lnk not in matched_links:
                                matched_links.append(lnk)
            if matched_links:
                lines[idx] = line.rstrip() + " (" + ", ".join(matched_links[:2]) + ")"
        cleaned = "\n".join(lines)

    # 4. Clean stray formatting artifacts (extra bullet spaces, empty parens/brackets, duplicate rules, broken bold tags)
    cleaned = re.sub(r"^(\s*[\*\-])\s{2,}", r"\1 ", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\(\s*\)|\[\s*\]", "", cleaned)
    cleaned = re.sub(r" +([,.;:])", r"\1", cleaned)
    cleaned = re.sub(r"(?m)^[\*\-]\s*$", "", cleaned)
    cleaned = re.sub(r"(?:\n\s*---\s*){2,}", "\n\n---\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def after_investigation_model(
    callback_context: CallbackContext, llm_response: LlmResponse
) -> Optional[LlmResponse]:
    """ADK after_model_callback: Captures Google Search grounding trace, source links, and follow-ups into session state."""
    if not llm_response or not llm_response.content or not llm_response.content.parts:
        return None

    # Ignore non-text intermediate responses (e.g., if a function_call part was emitted)
    response_text = "\n".join(
        p.text for p in llm_response.content.parts if getattr(p, "text", None)
    ).strip()
    if not response_text:
        return None

    state = callback_context.state

    # Re-verify session turn count & history from actual session events + state
    session_user_msgs, _, session_sources = _sync_state_from_session_events(callback_context)
    history = list(state.get("hypothesis_history", []))
    turn_num = max(int(state.get("turn_count", 1)), len(history), len(session_user_msgs), 1)
    state["turn_count"] = turn_num

    current_hyp = state.get("current_hypothesis", "")
    active_mode = state.get("active_mode", "initial_hypothesis" if turn_num == 1 else "revised_hypothesis")

    # 1. Extract Google Search queries & verified web sources from grounding_metadata
    turn_queries: list[str] = []
    turn_sources: list[dict[str, Any]] = []

    gm = llm_response.grounding_metadata
    if gm:
        if gm.web_search_queries:
            turn_queries = [q for q in gm.web_search_queries if q]
        if gm.grounding_chunks:
            seen_turn_urls: set[str] = set()
            for chunk in gm.grounding_chunks:
                if chunk.web and chunk.web.uri and chunk.web.uri not in seen_turn_urls:
                    seen_turn_urls.add(chunk.web.uri)
                    turn_sources.append(
                        {
                            "turn": turn_num,
                            "title": chunk.web.title or "Retrieved Web Source",
                            "url": chunk.web.uri,
                        }
                    )

    search_trace = list(state.get("search_trace", []))
    if turn_queries:
        # Update or append current turn's search trace
        search_trace = [st for st in search_trace if st.get("turn") != turn_num]
        search_trace.append(
            {
                "turn": turn_num,
                "hypothesis": current_hyp,
                "queries": turn_queries,
            }
        )
    state["search_trace"] = search_trace

    existing_sources = list(state.get("evidence_sources", []))
    seen_urls = {s.get("url") for s in existing_sources}
    for src in session_sources + turn_sources:
        if src["url"] not in seen_urls:
            existing_sources.append(src)
            seen_urls.add(src["url"])
    state["evidence_sources"] = existing_sources

    # 2. Clean response text, resolve inline citations to clickable links, and parse follow-ups
    cleaned_body = _inject_clickable_citations_and_clean_text(response_text, turn_sources, gm)
    parsed_followups = _parse_follow_ups_from_text(cleaned_body)
    if parsed_followups:
        state["suggested_follow_ups"] = parsed_followups

    reports = [r for r in list(state.get("investigation_reports", [])) if r.get("turn") != turn_num]
    reports.append(
        {
            "turn": turn_num,
            "mode": active_mode,
            "hypothesis": current_hyp,
            "queries_executed": turn_queries,
            "sources_retrieved_count": len(turn_sources),
            "follow_ups_offered": parsed_followups,
        }
    )
    state["investigation_reports"] = reports

    # Re-assign all notebook state keys so SqliteSessionService commits the full state_delta on this event
    state["notebook_initialized"] = True
    state["notebook_title"] = state.get(
        "notebook_title", "Culture Cross: The Ritual Detective — Investigation Notebook"
    )
    state["active_mode"] = active_mode
    state["current_hypothesis"] = current_hyp
    state["hypothesis_history"] = history
    state["notebook_context_prompt"] = _build_notebook_context(state)

    # 3. Build deterministic Provenance & Session Notebook footer from actual Python session.state
    cumulative_hypotheses_count = max(len(history), turn_num)
    cumulative_sources_count = len(existing_sources)

    footer_lines = ["\n\n---", "### 📓 Session Investigation Notebook & Provenance Trace"]
    footer_lines.append(
        f"- **Session Turn**: `{turn_num}` (`{active_mode}`) | "
        f"**Cumulative Hypotheses Tested**: `{cumulative_hypotheses_count}` | "
        f"**Cumulative Retrieved Grounding Sources**: `{cumulative_sources_count}`"
    )
    footer_lines.append(f"- **Active Hypothesis Investigated**: *{current_hyp}*")

    if turn_queries:
        q_str = ", ".join(f"`{q}`" for q in turn_queries)
        footer_lines.append(f"- **Google Search Queries Executed (Turn {turn_num})**: {q_str}")

    if turn_sources:
        footer_lines.append(f"- **Retrieved Grounding Sources (Turn {turn_num})**:")
        for idx, src in enumerate(turn_sources[:10], 1):
            footer_lines.append(f"  {idx}. [{src['title']}]({src['url']})")
    elif existing_sources:
        footer_lines.append("- **Retrieved Grounding Sources (Session Cumulative)**:")
        for idx, src in enumerate(existing_sources[-8:], 1):
            footer_lines.append(f"  {idx}. [{src['title']}]({src['url']})")

    footer_lines.append(
        "\n*💡 **Next Step**: Reply with **`1`**, **`2`**, or **`3`** to launch one of the "
        "Suggested Follow-Up Investigations above, or type a **revised hypothesis** to continue in this session.*"
    )

    # Write cleaned body + deterministic footer back into the response text part
    for i in range(len(llm_response.content.parts) - 1, -1, -1):
        if getattr(llm_response.content.parts[i], "text", None):
            llm_response.content.parts[i].text = cleaned_body + "\n" + "\n".join(footer_lines)
            break

    return llm_response
