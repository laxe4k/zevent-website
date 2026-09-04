import asyncio
import contextlib
import hashlib
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger("zevent-api")

load_dotenv()

UPSTREAM_URL = os.getenv("ZEVENT_UPSTREAM", "https://zevent.fr/api/")
POLL_INTERVAL = max(float(os.getenv("ZEVENT_POLL_INTERVAL", "30")), 5)
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]


class ZEventCache:
    def __init__(self) -> None:
        self.data: dict[str, Any] | None = None
        self.etag: str | None = None
        self.content_hash: str | None = None
        self.lock = asyncio.Lock()
        self.subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    async def refresh(self, client: httpx.AsyncClient) -> bool:
        headers = {"User-Agent": "zevent-dashboard/2.0"}
        if self.etag:
            headers["If-None-Match"] = self.etag

        response = await client.get(UPSTREAM_URL, headers=headers)
        if response.status_code == httpx.codes.NOT_MODIFIED:
            return False
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("La reponse ZEvent n'est pas un objet JSON")

        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        changed = payload_hash != self.content_hash

        async with self.lock:
            self.data = payload
            self.etag = response.headers.get("ETag")
            self.content_hash = payload_hash

        if changed:
            await self.broadcast(payload)
        return changed

    async def broadcast(self, payload: dict[str, Any]) -> None:
        message = {"type": "update", "timestamp": int(time.time()), "data": payload}
        for subscriber in tuple(self.subscribers):
            try:
                subscriber.put_nowait(message)
            except asyncio.QueueFull:
                self.subscribers.discard(subscriber)


cache = ZEventCache()


async def poll(cache_client: httpx.AsyncClient) -> None:
    while True:
        try:
            await cache.refresh(cache_client)
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("Impossible de recuperer les donnees ZEvent: %s", error)
        await asyncio.sleep(POLL_INTERVAL)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        try:
            await cache.refresh(client)
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("Cache ZEvent non initialise: %s", error)

        poll_task = asyncio.create_task(poll(client))
        try:
            yield
        finally:
            poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await poll_task


app = FastAPI(title="ZEvent API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


async def get_data() -> dict[str, Any]:
    if cache.data is None:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            try:
                await cache.refresh(client)
            except (httpx.HTTPError, ValueError) as error:
                raise HTTPException(
                    status_code=502,
                    detail="Les donnees ZEvent sont indisponibles",
                ) from error
    return cache.data or {}


def amount(value: Any) -> int | float:
    if isinstance(value, dict):
        value = value.get("number", 0)
    return value if isinstance(value, (int, float)) else 0


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "cached": cache.data is not None}


@app.get("/api/raw")
async def raw_data() -> JSONResponse:
    return JSONResponse(await get_data(), headers={"Cache-Control": "no-store"})


@app.get("/api/summary")
async def summary() -> JSONResponse:
    data = await get_data()
    fields = ("globalDonationUrl", "donationAmount", "viewersCount", "websiteMode")
    return JSONResponse(
        {field: data.get(field) for field in fields},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/streamers")
async def streamers(
    q: str = "", online: bool | None = None, sort: str = "donationDesc"
) -> JSONResponse:
    data = await get_data()
    query = q.strip().lower()
    items = []
    for streamer in data.get("live", []):
        if not isinstance(streamer, dict):
            continue
        is_online = bool(streamer.get("online"))
        searchable = f"{streamer.get('display', '')} {streamer.get('twitch', '')}".lower()
        if online is not None and is_online != online:
            continue
        if query and query not in searchable:
            continue
        items.append(
            {
                "display": streamer.get("display"),
                "twitch": streamer.get("twitch"),
                "online": is_online,
                "game": streamer.get("game"),
                "location": streamer.get("location"),
                "viewers": amount(streamer.get("viewersAmount")),
                "donation": amount(streamer.get("donationAmount")),
                "donationUrl": streamer.get("donationUrl"),
                "profileUrl": streamer.get("profileUrl"),
            }
        )

    sorters = {
        "viewersDesc": lambda item: item["viewers"],
        "nameAsc": lambda item: str(item["display"] or "").lower(),
        "onlineFirst": lambda item: (not item["online"], -item["viewers"]),
        "donationDesc": lambda item: item["donation"],
    }
    key = sorters.get(sort, sorters["donationDesc"])
    items.sort(key=key, reverse=sort in {"viewersDesc", "donationDesc"})
    return JSONResponse({"count": len(items), "items": items})


@app.get("/events")
async def events(request: Request) -> StreamingResponse:
    subscriber: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=10)
    cache.subscribers.add(subscriber)

    async def event_stream() -> AsyncIterator[str]:
        if cache.data is not None:
            snapshot = {"type": "snapshot", "timestamp": int(time.time()), "data": cache.data}
            yield f"data: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
        try:
            while not await request.is_disconnected():
                try:
                    message = await asyncio.wait_for(subscriber.get(), timeout=20)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps(message, ensure_ascii=False)}\n\n"
        finally:
            cache.subscribers.discard(subscriber)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
