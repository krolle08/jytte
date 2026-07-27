import os
import logging

log = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("JYTTE_CLAUDE_MODEL", "claude-haiku-4-5-20251001")


def _client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        return None
    return AsyncAnthropic(api_key=api_key)


async def analyze(system: str, user: str, model: str | None = None, max_tokens: int = 1024) -> str | None:
    client = _client()
    if client is None:
        log.info("ANTHROPIC_API_KEY missing - skipping analyze call")
        return None
    try:
        resp = await client.messages.create(
            model=model or DEFAULT_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [block.text for block in resp.content if getattr(block, "type", "") == "text"]
        return "\n".join(parts).strip()
    except Exception as e:
        log.exception("Claude analyze failed: %s", e)
        return None


async def chat_with_context(message: str, summaries: dict[str, str]) -> str:
    client = _client()
    if client is None:
        return "[Claude API key not configured - chat unavailable]"
    context_lines = [f"## {name}\n{summary}" for name, summary in summaries.items() if summary]
    context_block = "\n\n".join(context_lines) if context_lines else "(no widget summaries available)"
    system = (
        "You are Jytte, a personal Jarvis-style assistant for Nichlas. "
        "Answer using only the widget summaries below as factual context. "
        "Be concise. If the user asks about something not covered by the summaries, "
        "say so plainly instead of inventing.\n\n"
        f"# Widget summaries\n{context_block}"
    )
    try:
        resp = await client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": message}],
        )
        parts = [block.text for block in resp.content if getattr(block, "type", "") == "text"]
        return "\n".join(parts).strip()
    except Exception as e:
        log.exception("Claude chat failed: %s", e)
        return f"[Claude call failed: {e}]"
