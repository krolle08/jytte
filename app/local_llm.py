"""A local model through Ollama, for analyzers that should not cost an
API key.

Ollama runs natively on the Windows host, not in compose: the Docker
Desktop VM has 2 GB of memory, and a 7B model needs about 5 GB. The
container reaches it at host.docker.internal.

Same contract as claude.analyze(): text back, or None when the model
is unreachable, so a caller can keep its previous result. `schema`
is passed as Ollama's `format`, which constrains decoding to that JSON
schema. A small model drifts from a schema it is only told about in
the prompt; one it is decoded against cannot.
"""
from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger(__name__)

URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
DEFAULT_MODEL = os.getenv("JYTTE_LOCAL_MODEL", "qwen2.5:7b")
# CPU inference writes a few tokens a second, so a long JSON note takes
# minutes. The analyzer runs on the scheduler, never in a request.
TIMEOUT = float(os.getenv("JYTTE_LOCAL_TIMEOUT", "3600"))


async def analyze(system: str, user: str, model: str | None = None,
                  schema: dict | None = None, num_ctx: int = 16384,
                  max_tokens: int = 12000) -> str | None:
    body = {
        "model": model or DEFAULT_MODEL,
        "stream": False,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "options": {"temperature": 0, "num_ctx": num_ctx, "num_predict": max_tokens},
    }
    if schema is not None:
        body["format"] = schema
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(f"{URL}/api/chat", json=body)
            r.raise_for_status()
            return (r.json().get("message") or {}).get("content", "").strip() or None
    except Exception as e:
        log.warning("local model call failed (%s at %s): %s", body["model"], URL, e)
        return None


async def reachable() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            return (await client.get(f"{URL}/api/tags")).status_code == 200
    except Exception:
        return False
