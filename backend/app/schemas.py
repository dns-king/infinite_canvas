from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GenerateTileRequest(BaseModel):
    x: int
    y: int
    seed: int = 1337
    biome: str = Field(default="forest", min_length=1, max_length=64)
    prompt: str | None = Field(default=None, max_length=512)
    lod: int = Field(default=512, ge=128, le=512)
    priority: float = 0.0


class TileStats(BaseModel):
    hits: int
    misses: int
    size: int
    max_size: int


class TileResponseMeta(BaseModel):
    x: int
    y: int
    seed: int
    biome: str
    lod: int
    cached: bool
    latency_ms: float
    cache: TileStats


class TileWebSocketMessage(BaseModel):
    type: str
    requestId: str | None = None
    x: int | None = None
    y: int | None = None
    seed: int = 1337
    biome: str = "forest"
    prompt: str | None = None
    lod: int = 512
    cameraX: float | None = None
    cameraZ: float | None = None
    velocityX: float = 0.0
    velocityZ: float = 0.0
    radius: int = 3


class WebSocketTilePayload(BaseModel):
    type: str = "tile"
    requestId: str
    x: int
    y: int
    seed: int
    biome: str
    lod: int
    dataUrl: str
    meta: dict[str, Any]

