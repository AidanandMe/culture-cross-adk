import asyncio
import os
import sys
from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner
from google.genai import types

# Ensure UTF-8 output on Windows consoles
sys.stdout.reconfigure(encoding="utf-8")

# Load .env with override=True before importing agent
load_dotenv(".env", override=True)

from ritual_detective.agent import root_agent  # noqa: E402


async def main() -> None:
    key = os.getenv("GOOGLE_API_KEY", "")
    print(f"GOOGLE_API_KEY configured from .env: {bool(key and key != 'your_google_ai_studio_api_key_here')}")
    print(f"Agent: {root_agent.name} | Model: {root_agent.model} | Tools: {[t.__name__ if hasattr(t, '__name__') else type(t).__name__ for t in root_agent.tools]}")
    print("=" * 70)

    runner = InMemoryRunner(agent=root_agent, app_name="culture_cross")
    session = await runner.session_service.create_session(
        app_name="culture_cross", user_id="player_1"
    )

    prompt = (
        "Hypothesis: Did Halloween and Mexico's Día de los Muertos originate "
        "from the same ancient festival?"
    )
    print(f"USER HYPOTHESIS:\n{prompt}\n" + "=" * 70)

    msg = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])

    async for event in runner.run_async(
        user_id="player_1", session_id=session.id, new_message=msg
    ):
        if event.grounding_metadata:
            queries = event.grounding_metadata.web_search_queries
            if queries:
                print("\n[ADK GOOGLE SEARCH QUERIES EXECUTED]")
                for q in queries:
                    print(f"  - {q}")
            chunks = event.grounding_metadata.grounding_chunks
            if chunks:
                print(f"\n[ADK GROUNDING - {len(chunks)} VERIFIED WEB SOURCES RETRIEVED]")
                for idx, chunk in enumerate(chunks, 1):
                    if chunk.web:
                        print(f"  [{idx}] {chunk.web.title} -> {chunk.web.uri}")

        if event.is_final_response() and event.content and event.content.parts:
            print("\n" + "=" * 70 + "\n[AGENT FINAL RESPONSE]\n" + "=" * 70)
            for part in event.content.parts:
                if part.text:
                    print(part.text)


if __name__ == "__main__":
    asyncio.run(main())
