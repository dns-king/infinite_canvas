from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


@dataclass(frozen=True)
class Settings:
    tile_size: int = _int_env("INFINITE_CANVAS_TILE_SIZE", 512)
    context_px: int = _int_env("INFINITE_CANVAS_CONTEXT_PX", 128)
    generator: str = os.getenv("INFINITE_CANVAS_GENERATOR", "procedural").lower()
    model_id: str = os.getenv("INFINITE_CANVAS_MODEL_ID", "runwayml/stable-diffusion-v1-5")
    inpaint_model_id: str = os.getenv(
        "INFINITE_CANVAS_INPAINT_MODEL_ID",
        "runwayml/stable-diffusion-inpainting",
    )
    device: str = os.getenv("INFINITE_CANVAS_DEVICE", "auto")
    diffusion_steps: int = _int_env("INFINITE_CANVAS_DIFFUSION_STEPS", 10)
    guidance_scale: float = _float_env("INFINITE_CANVAS_GUIDANCE_SCALE", 5.0)
    max_concurrent_generations: int = _int_env("INFINITE_CANVAS_MAX_CONCURRENT", 1)
    cache_max_tiles: int = _int_env("INFINITE_CANVAS_CACHE_MAX_TILES", 96)
    cache_ttl_seconds: int = _int_env("INFINITE_CANVAS_CACHE_TTL_SECONDS", 3600)
    prefetch_radius: int = _int_env("INFINITE_CANVAS_PREFETCH_RADIUS", 3)
    prefetch_lead_tiles: int = _int_env("INFINITE_CANVAS_PREFETCH_LEAD_TILES", 3)
    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv(
            "INFINITE_CANVAS_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    )
    negative_prompt: str = os.getenv(
        "INFINITE_CANVAS_NEGATIVE_PROMPT",
        "hard seams, borders, frames, text, watermark, low resolution, blurry",
    )

    @property
    def canvas_size(self) -> int:
        return self.tile_size + self.context_px * 2


settings = Settings()

