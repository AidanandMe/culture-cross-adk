import asyncio
import re
import sys
from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner

# Ensure UTF-8 output on Windows consoles
sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(".env", override=True)

from ritual_detective.agent import root_agent  # noqa: E402
from ritual_detective.notebook import _inject_clickable_citations_and_clean_text  # noqa: E402
from notebook_cli import print_notebook_state, run_turn  # noqa: E402


def verify_citation_cleaning_unit() -> None:
    """Verifies that bracket references like [1.2.5] or [1, 2] resolve to clickable links or are cleanly stripped."""
    sample_sources = [
        {"turn": 1, "title": "britannica.com", "url": "https://www.britannica.com/topic/Halloween"},
        {"turn": 1, "title": "rutgers.edu", "url": "https://www.rutgers.edu/news/day-of-the-dead"},
        {"turn": 1, "title": "ku.edu", "url": "https://spencer.lib.ku.edu/dia-de-muertos"},
        {"turn": 1, "title": "english-heritage.org.uk", "url": "https://www.english-heritage.org.uk/halloween"},
        {"turn": 1, "title": "horniman.ac.uk", "url": "https://www.horniman.ac.uk/day-of-the-dead"},
    ]
    raw_text = (
        "* **Spanish-Mesoamerican Syncretism**: Friars observed Indigenous commemorations [1.2.5] "
        "and shifted them to November [1, 2]. Unresolvable ref [9.9.99]."
    )
    cleaned = _inject_clickable_citations_and_clean_text(raw_text, sample_sources, None)
    assert "[1.2.5]" not in cleaned, "Unlinked [1.2.5] should be resolved or stripped"
    assert "[9.9.99]" not in cleaned, "Unresolvable [9.9.99] should be stripped"
    assert "[horniman.ac.uk](https://www.horniman.ac.uk/day-of-the-dead)" in cleaned
    assert "[britannica.com](https://www.britannica.com/topic/Halloween)" in cleaned
    print("✅ Unit check passed: [1.2.5] and [1, 2] resolved to clickable URLs; unresolvable brackets stripped.")


async def verify_two_turns() -> None:
    verify_citation_cleaning_unit()

    runner = InMemoryRunner(agent=root_agent, app_name="culture_cross")
    user_id = "detective_player"
    session = await runner.session_service.create_session(
        app_name="culture_cross", user_id=user_id
    )

    # =========================================================================
    # TURN 1: Submit initial cultural hypothesis
    # =========================================================================
    turn1_input = (
        "Did Halloween and Mexico's Día de los Muertos originate from the same ancient festival?"
    )
    print("\n" + "=" * 75)
    print(f"🚀 TURN 1 PLAYER INPUT:\n{turn1_input}")
    print("=" * 75)

    state_after_t1 = await run_turn(runner, user_id, session.id, turn1_input)
    print_notebook_state(state_after_t1)

    t1_sources = len(state_after_t1.get("evidence_sources", []))
    assert state_after_t1.get("turn_count") == 1, f"Expected turn_count == 1, got {state_after_t1.get('turn_count')}"
    assert len(state_after_t1.get("hypothesis_history", [])) == 1
    assert t1_sources > 0, f"Expected > 0 verified sources on Turn 1, got {t1_sources}"

    # =========================================================================
    # TURN 2: Submit the user's exact second question in the SAME session
    # =========================================================================
    turn2_input = (
        'So, did they merge in some way because of the cultural contact '
        'after the so called "discovery of Americas"?'
    )
    print("\n" + "=" * 75)
    print(f"🚀 TURN 2 PLAYER INPUT (Same Session {session.id}):\n{turn2_input}")
    print("=" * 75)

    state_after_t2 = await run_turn(runner, user_id, session.id, turn2_input)
    print_notebook_state(state_after_t2)

    t2_sources = len(state_after_t2.get("evidence_sources", []))
    assert state_after_t2.get("turn_count") == 2, f"Expected turn_count == 2, got {state_after_t2.get('turn_count')}"
    assert len(state_after_t2.get("hypothesis_history", [])) == 2
    assert len(state_after_t2.get("search_trace", [])) == 2
    assert t2_sources >= t1_sources and t2_sources > 0, f"Expected cumulative sources > 0, got {t2_sources}"

    # Verify the rendered Turn 2 message in session.events has accurate footer & no unlinked [1.2.5]
    updated_session = await runner.session_service.get_session(
        app_name="culture_cross", user_id=user_id, session_id=session.id
    )
    last_model_texts = [
        p.text
        for ev in updated_session.events
        if ev.author == "ritual_detective" and ev.content and ev.content.parts
        for p in ev.content.parts
        if getattr(p, "text", None)
    ]
    last_text = last_model_texts[-1]
    assert "**Session Turn**: `2`" in last_text, "Turn 2 footer must show Session Turn: 2"
    assert "**Cumulative Hypotheses Tested**: `2`" in last_text, "Turn 2 footer must show Cumulative Hypotheses Tested: 2"
    assert "**Cumulative Retrieved Grounding Sources**: `0`" not in last_text, "Cumulative Retrieved Grounding Sources must not be 0"
    assert "**Retrieved Grounding Sources (Turn 2)**:" in last_text, "Turn 2 footer must show Retrieved Grounding Sources"
    assert not re.search(r"\[\d+\.\d+\.\d+\]", last_text), "No unlinked [x.y.z] references allowed"

    print("✅ TWO-TURN ADK SESSION NOTEBOOK & PROVENANCE WORKFLOW VERIFIED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(verify_two_turns())
