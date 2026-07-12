from __future__ import annotations

import asyncio
import base64
import time
from dataclasses import dataclass
from typing import Any

from PIL import Image

from .cache import TileCache, TileKey
from .config import Settings, settings
from .coords import (
    deterministic_tile_seed,
    manhattan_priority,
    predictive_tile_coords,
    visible_tile_coords,
    world_to_tile_coords,
)
from .generators import (
    NeighborImages,
    ProceduralTileGenerator,
    TileGenerationContext,
    TileGenerator,
    image_to_png_bytes,
    png_bytes_to_image,
)
from .infinite_diffusion import StableDiffusionInfinitePipeline
from .schemas import GenerateTileRequest, TileResponseMeta


@dataclass
class TileResult:
    data: bytes
    meta: TileResponseMeta

    @property
    def data_url(self) -> str:
        encoded = base64.b64encode(self.data).decode("ascii")
        return f"data:image/png;base64,{encoded}"


class TileService:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self.cache = TileCache(config.cache_max_tiles, config.cache_ttl_seconds)
        self.generator = self._build_generator(config)
        self._semaphore = asyncio.Semaphore(config.max_concurrent_generations)
        self._prefetch_queue: asyncio.PriorityQueue[
            tuple[float, int, GenerateTileRequest]
        ] = asyncio.PriorityQueue()
        self._prefetch_worker: asyncio.Task[None] | None = None
        self._queue_counter = 0

    async def start(self) -> None:
        if self._prefetch_worker is None or self._prefetch_worker.done():
            self._prefetch_worker = asyncio.create_task(self._prefetch_loop())

    async def stop(self) -> None:
        if self._prefetch_worker is not None:
            self._prefetch_worker.cancel()
            try:
                await self._prefetch_worker
            except asyncio.CancelledError:
                pass

    async def get_tile(self, request: GenerateTileRequest) -> TileResult:
        normalized = self._normalize_request(request)
        key = self._key(normalized)
        started = time.perf_counter()
        entry = await self.cache.get(key)
        if entry is not None:
            meta = await self._meta(normalized, cached=True, started=started)
            return TileResult(data=entry.data, meta=meta)

        async with self._semaphore:
            entry = await self.cache.get(key)
            if entry is not None:
                meta = await self._meta(normalized, cached=True, started=started)
                return TileResult(data=entry.data, meta=meta)

            neighbors = await self._neighbor_images(normalized)
            ctx = TileGenerationContext(
                x=normalized.x,
                y=normalized.y,
                seed=normalized.seed,
                biome=normalized.biome,
                prompt=normalized.prompt,
                size=normalized.lod,
                world_span_px=self.config.tile_size,
                context_px=min(self.config.context_px, normalized.lod // 3),
                neighbors=neighbors,
            )
            image = await asyncio.to_thread(self.generator.generate, ctx)
            data = image_to_png_bytes(image)
            await self.cache.put(
                key,
                data,
                metadata={
                    "source": self.config.generator,
                    "seed": deterministic_tile_seed(normalized.x, normalized.y, normalized.seed),
                },
            )
            meta = await self._meta(normalized, cached=False, started=started)
            return TileResult(data=data, meta=meta)

    async def schedule_prefetch(
        self,
        camera_x: float,
        camera_z: float,
        velocity_x: float,
        velocity_z: float,
        seed: int,
        biome: str,
        prompt: str | None,
        radius: int,
        tile_world_size: float,
    ) -> int:
        center = world_to_tile_coords(camera_x, camera_z, tile_world_size)
        coords = predictive_tile_coords(
            center,
            (velocity_x, velocity_z),
            min(radius, self.config.prefetch_radius),
            self.config.prefetch_lead_tiles,
        )
        if not coords:
            coords = visible_tile_coords(center, min(radius, self.config.prefetch_radius))

        queued = 0
        for priority, coord in manhattan_priority(center, coords):
            request = GenerateTileRequest(
                x=coord[0],
                y=coord[1],
                seed=seed,
                biome=biome,
                prompt=prompt,
                lod=self._low_lod() if priority > radius else self._high_lod(),
                priority=priority,
            )
            key = self._key(self._normalize_request(request))
            if await self.cache.peek(key) is not None:
                continue
            self._queue_counter += 1
            await self._prefetch_queue.put((priority, self._queue_counter, request))
            queued += 1
        return queued

    async def _prefetch_loop(self) -> None:
        while True:
            _, _, request = await self._prefetch_queue.get()
            try:
                await self.get_tile(request)
            except Exception:
                pass
            finally:
                self._prefetch_queue.task_done()

    async def _neighbor_images(self, request: GenerateTileRequest) -> NeighborImages:
        positions = {
            "left": (request.x - 1, request.y),
            "right": (request.x + 1, request.y),
            "top": (request.x, request.y - 1),
            "bottom": (request.x, request.y + 1),
        }
        neighbors: NeighborImages = {}
        for side, (x, y) in positions.items():
            entry = await self.cache.peek((x, y, request.seed, request.biome, request.lod, request.prompt))
            if entry is None:
                continue
            try:
                neighbors[side] = png_bytes_to_image(entry.data)
            except Exception:
                continue
        return neighbors

    async def _meta(
        self,
        request: GenerateTileRequest,
        cached: bool,
        started: float,
    ) -> TileResponseMeta:
        return TileResponseMeta(
            x=request.x,
            y=request.y,
            seed=request.seed,
            biome=request.biome,
            lod=request.lod,
            cached=cached,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            cache=await self.cache.stats(),
        )

    def _normalize_request(self, request: GenerateTileRequest) -> GenerateTileRequest:
        lod = self._low_lod() if request.lod <= self._low_lod() else self._high_lod()
        biome = request.biome.strip().lower()
        prompt = request.prompt.strip() if request.prompt else None
        if prompt == "":
            prompt = None
        return GenerateTileRequest(
            x=request.x,
            y=request.y,
            seed=request.seed,
            biome=biome,
            prompt=prompt,
            lod=lod,
            priority=request.priority,
        )

    def _key(self, request: GenerateTileRequest) -> TileKey:
        return (request.x, request.y, request.seed, request.biome, request.lod, request.prompt)

    def _high_lod(self) -> int:
        return max(128, self.config.tile_size)

    def _low_lod(self) -> int:
        return max(128, self._high_lod() // 2)

    def _build_generator(self, config: Settings) -> TileGenerator:
        if config.generator == "diffusers":
            return StableDiffusionInfinitePipeline(
                model_id=config.model_id,
                inpaint_model_id=config.inpaint_model_id,
                negative_prompt=config.negative_prompt,
                steps=config.diffusion_steps,
                guidance_scale=config.guidance_scale,
                device=config.device,
            )
        return ProceduralTileGenerator()


tile_service = TileService()
