import asyncio
import io

import numpy as np
from PIL import Image

from app.config import Settings
from app.schemas import GenerateTileRequest
from app.tile_service import TileService


def test_procedural_tiles_are_deterministic() -> None:
    async def run() -> None:
        service = TileService(make_settings())
        request = GenerateTileRequest(x=4, y=-2, seed=99, biome="forest", lod=128)
        first = await service.get_tile(request)
        second = await service.get_tile(request)
        assert first.data == second.data
        assert second.meta.cached is True

    asyncio.run(run())


def test_adjacent_tiles_have_low_edge_delta() -> None:
    async def run() -> None:
        service = TileService(make_settings())
        a = await service.get_tile(GenerateTileRequest(x=0, y=0, seed=7, biome="alien", lod=128))
        b = await service.get_tile(GenerateTileRequest(x=1, y=0, seed=7, biome="alien", lod=128))
        c = await service.get_tile(GenerateTileRequest(x=0, y=1, seed=7, biome="alien", lod=128))

        img_a = image_array(a.data)
        img_b = image_array(b.data)
        img_c = image_array(c.data)

        horizontal_delta = np.abs(img_a[:, -1, :].astype(int) - img_b[:, 0, :].astype(int)).mean()
        vertical_delta = np.abs(img_a[-1, :, :].astype(int) - img_c[0, :, :].astype(int)).mean()
        assert horizontal_delta < 22
        assert vertical_delta < 22

    asyncio.run(run())


def image_array(data: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))


def make_settings() -> Settings:
    return Settings(
        tile_size=128,
        context_px=32,
        generator="procedural",
        cache_max_tiles=16,
        cache_ttl_seconds=300,
        max_concurrent_generations=1,
    )
