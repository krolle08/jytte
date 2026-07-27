import asyncio
import json
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

sse_router = APIRouter()
_subscribers: set[asyncio.Queue] = set()


async def publish(event: str, data: dict) -> None:
    payload = {"event": event, "data": json.dumps(data)}
    for q in list(_subscribers):
        await q.put(payload)


@sse_router.get("/events")
async def events(request: Request):
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers.add(queue)

    async def stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield msg
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            _subscribers.discard(queue)

    return EventSourceResponse(stream())
