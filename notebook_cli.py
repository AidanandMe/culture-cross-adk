import asyncio
import json
import sys
from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner
from google.genai import types

# Ensure UTF-8 output on Windows consoles
sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(".env", override=True)

from ritual_detective.agent import root_agent  # noqa: E402


def print_notebook_state(state: dict) -> None:
    """Prints a readable summary of the ADK session.state Investigation Notebook."""
    print("\n" + "=" * 75)
    print(f"📓 ADK SESSION STATE: {state.get('notebook_title', 'Investigation Notebook')}")
    print("=" * 75)
    print(f"• Turns Completed: {state.get('turn_count', 0)}")
    print(f"• Current Mode:    {state.get('active_mode', '')}")
    print(f"• Active Lead:     {state.get('current_hypothesis', '')}")

    print("\n• Hypothesis History:")
    for h in state.get("hypothesis_history", []):
        print(
            f"  [Turn {h['turn']} | {h['mode']}] "
            f"Input: {h['player_input']!r} -> Resolved: {h['resolved_hypothesis']}"
        )

    print("\n• Cumulative Search Trace (Google Search Grounding):")
    for st in state.get("search_trace", []):
        print(f"  [Turn {st['turn']}] Queries: {st['queries']}")

    sources = state.get("evidence_sources", [])
    print(f"\n• Cumulative Retrieved Grounding Sources ({len(sources)} total):")
    for idx, src in enumerate(sources[:12], 1):
        print(f"  [{idx}] (Turn {src['turn']}) {src['title']} -> {src['url']}")

    follow_ups = state.get("suggested_follow_ups", [])
    if follow_ups:
        print("\n• Active Suggested Follow-Up Investigations (Reply 1, 2, or 3):")
        for idx, fu in enumerate(follow_ups, 1):
            print(f"  [{idx}] {fu}")
    print("=" * 75 + "\n")


async def run_turn(
    runner: InMemoryRunner, user_id: str, session_id: str, player_input: str
) -> dict:
    """Executes one turn in the existing ADK session and returns updated session.state."""
    msg = types.Content(role="user", parts=[types.Part.from_text(text=player_input)])

    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=msg
    ):
        if event.is_final_response() and event.content and event.content.parts:
            print("\n" + "-" * 75)
            for part in event.content.parts:
                if part.text:
                    print(part.text)
            print("-" * 75)

    updated_session = await runner.session_service.get_session(
        app_name="culture_cross", user_id=user_id, session_id=session_id
    )
    return dict(updated_session.state) if updated_session else {}


async def interactive_loop() -> None:
    runner = InMemoryRunner(agent=root_agent, app_name="culture_cross")
    user_id = "detective_player"
    session = await runner.session_service.create_session(
        app_name="culture_cross", user_id=user_id
    )

    print("=" * 75)
    print("🕵️  CULTURE CROSS: THE RITUAL DETECTIVE — Interactive ADK Notebook")
    print("=" * 75)
    print("Commands:")
    print("  • Enter any cultural hypothesis to investigate.")
    print("  • Enter 1, 2, or 3 after a report to select a Follow-Up Investigation.")
    print("  • Enter 'state' to inspect the live ADK session.state notebook.")
    print("  • Enter 'quit' to exit.\n")

    while True:
        try:
            user_input = input("Detective Input > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting notebook.")
            break

        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit", "q"}:
            break
        if user_input.lower() == "state":
            curr = await runner.session_service.get_session(
                app_name="culture_cross", user_id=user_id, session_id=session.id
            )
            if curr:
                print_notebook_state(dict(curr.state))
                print(json.dumps(dict(curr.state), indent=2, ensure_ascii=False))
            continue

        state = await run_turn(runner, user_id, session.id, user_input)
        print_notebook_state(state)


if __name__ == "__main__":
    asyncio.run(interactive_loop())
