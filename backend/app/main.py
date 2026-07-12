from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .config import settings
from .schemas import GenerateTileRequest, TileWebSocketMessage, WebSocketTilePayload
from .tile_service import tile_service

app = FastAPI(title="InfiniteCanvas Tile Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    await tile_service.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    await tile_service.stop()


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "generator": settings.generator,
        "tileSize": settings.tile_size,
        "contextPx": settings.context_px,
        "cache": (await tile_service.cache.stats()).model_dump(),
    }


@app.post("/generate_tile")
async def generate_tile(request: GenerateTileRequest) -> Response:
    try:
        result = await tile_service.get_tile(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(
        content=result.data,
        media_type="image/png",
        headers={
            "X-InfiniteCanvas-Meta": result.meta.model_dump_json(),
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )


@app.websocket("/ws/tiles")
async def tile_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    send_lock = _SendLock()
    tasks: set = set()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = TileWebSocketMessage.model_validate(json.loads(raw))
            except Exception as exc:
                await send_lock.send(websocket, {"type": "error", "message": f"Invalid message: {exc}"})
                continue

            if message.type == "tile.request":
                if message.requestId is None or message.x is None or message.y is None:
                    await send_lock.send(
                        websocket,
                        {"type": "error", "message": "tile.request requires requestId, x, and y"},
                    )
                    continue
                task = _spawn_tile_task(websocket, send_lock, message)
                tasks.add(task)
                task.add_done_callback(tasks.discard)
            elif message.type == "tile.prefetch":
                queued = await tile_service.schedule_prefetch(
                    camera_x=message.cameraX or 0.0,
                    camera_z=message.cameraZ or 0.0,
                    velocity_x=message.velocityX,
                    velocity_z=message.velocityZ,
                    seed=message.seed,
                    biome=message.biome,
                    prompt=message.prompt,
                    radius=message.radius,
                    tile_world_size=32.0,
                )
                await send_lock.send(websocket, {"type": "prefetch.queued", "queued": queued})
            elif message.type == "ping":
                await send_lock.send(websocket, {"type": "pong"})
            else:
                await send_lock.send(websocket, {"type": "error", "message": f"Unknown type {message.type}"})
    except WebSocketDisconnect:
        pass
    finally:
        for task in tasks:
            task.cancel()


def _spawn_tile_task(websocket: WebSocket, send_lock: "_SendLock", message: TileWebSocketMessage):
    import asyncio

    async def run() -> None:
        request = GenerateTileRequest(
            x=message.x or 0,
            y=message.y or 0,
            seed=message.seed,
            biome=message.biome,
            prompt=message.prompt,
            lod=message.lod,
        )
        try:
            result = await tile_service.get_tile(request)
            payload = WebSocketTilePayload(
                requestId=message.requestId or "",
                x=request.x,
                y=request.y,
                seed=request.seed,
                biome=request.biome,
                lod=256 if request.lod <= 256 else 512,
                dataUrl=result.data_url,
                meta=result.meta.model_dump(),
            )
            await send_lock.send(websocket, payload.model_dump())
        except Exception as exc:
            await send_lock.send(
                websocket,
                {
                    "type": "tile.error",
                    "requestId": message.requestId,
                    "x": message.x,
                    "y": message.y,
                    "message": str(exc),
                },
            )

    return asyncio.create_task(run())


class _SendLock:
    def __init__(self) -> None:
        import asyncio

        self._lock = asyncio.Lock()

    async def send(self, websocket: WebSocket, payload: dict) -> None:
        async with self._lock:
            await websocket.send_json(payload)

