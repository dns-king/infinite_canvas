from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from PIL import Image, ImageFilter

from .coords import deterministic_tile_seed


NeighborImages = dict[str, Image.Image]


BIOME_PROMPTS: dict[str, str] = {
    "forest": "lush temperate forest canopy, mossy rock shelves, small streams, cinematic aerial texture",
    "desert": "wind carved desert badlands, dunes, dry river beds, sandstone strata, cinematic aerial texture",
    "ocean": "tropical shallow ocean, reefs, sandbars, deep blue channels, cinematic aerial texture",
    "alien": "alien planet terrain, glowing mineral veins, violet moss, teal craters, cinematic aerial texture",
}


@dataclass(frozen=True)
class TileGenerationContext:
    x: int
    y: int
    seed: int
    biome: str
    prompt: str | None
    size: int
    world_span_px: int
    context_px: int
    neighbors: NeighborImages

    @property
    def effective_prompt(self) -> str:
        if self.prompt:
            return self.prompt
        return BIOME_PROMPTS.get(self.biome, BIOME_PROMPTS["forest"])


class TileGenerator(Protocol):
    def generate(self, ctx: TileGenerationContext) -> Image.Image:
        ...


def image_to_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def png_bytes_to_image(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGB")


def _smoothstep(t: np.ndarray) -> np.ndarray:
    return t * t * (3.0 - 2.0 * t)


def _hash_grid(ix: np.ndarray, iy: np.ndarray, seed: int) -> np.ndarray:
    n = ix.astype(np.int64) * 374761393 + iy.astype(np.int64) * 668265263 + seed * 1442695041
    n = (n ^ (n >> 13)) * 1274126177
    n = n ^ (n >> 16)
    return (n & 0xFFFFFFFF).astype(np.float32) / np.float32(0xFFFFFFFF)


def _value_noise(x: np.ndarray, y: np.ndarray, scale: float, seed: int) -> np.ndarray:
    sx = x / scale
    sy = y / scale
    x0 = np.floor(sx).astype(np.int64)
    y0 = np.floor(sy).astype(np.int64)
    xf = _smoothstep((sx - x0).astype(np.float32))
    yf = _smoothstep((sy - y0).astype(np.float32))

    v00 = _hash_grid(x0, y0, seed)
    v10 = _hash_grid(x0 + 1, y0, seed)
    v01 = _hash_grid(x0, y0 + 1, seed)
    v11 = _hash_grid(x0 + 1, y0 + 1, seed)
    a = v00 * (1.0 - xf) + v10 * xf
    b = v01 * (1.0 - xf) + v11 * xf
    return a * (1.0 - yf) + b * yf


def _fractal_noise(x: np.ndarray, y: np.ndarray, seed: int) -> np.ndarray:
    value = np.zeros_like(x, dtype=np.float32)
    amplitude = 0.58
    total = 0.0
    for octave, scale in enumerate((420.0, 210.0, 96.0, 44.0, 20.0, 9.0)):
        value += _value_noise(x, y, scale, seed + octave * 1013) * amplitude
        total += amplitude
        amplitude *= 0.52
    return value / total


def _palette(biome: str) -> np.ndarray:
    palettes = {
        "forest": np.array(
            [
                [21, 55, 43],
                [37, 96, 56],
                [82, 128, 71],
                [146, 154, 101],
                [221, 209, 161],
            ],
            dtype=np.float32,
        ),
        "desert": np.array(
            [
                [77, 54, 47],
                [139, 91, 58],
                [202, 142, 83],
                [229, 188, 121],
                [245, 227, 171],
            ],
            dtype=np.float32,
        ),
        "ocean": np.array(
            [
                [6, 34, 74],
                [9, 79, 122],
                [18, 139, 151],
                [116, 192, 172],
                [236, 221, 157],
            ],
            dtype=np.float32,
        ),
        "alien": np.array(
            [
                [31, 21, 52],
                [72, 52, 122],
                [49, 138, 143],
                [141, 197, 112],
                [238, 212, 111],
            ],
            dtype=np.float32,
        ),
    }
    return palettes.get(biome, palettes["forest"])


def _colorize(height: np.ndarray, detail: np.ndarray, biome: str) -> np.ndarray:
    palette = _palette(biome)
    t = np.clip(height * 0.82 + detail * 0.18, 0.0, 0.999)
    scaled = t * (len(palette) - 1)
    idx = np.floor(scaled).astype(np.int32)
    frac = (scaled - idx)[..., None]
    colors = palette[idx] * (1.0 - frac) + palette[np.clip(idx + 1, 0, len(palette) - 1)] * frac
    return colors


def _apply_lighting(colors: np.ndarray, height: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(height)
    light = np.array([-0.55, -0.72, 0.84], dtype=np.float32)
    normal = np.dstack((-gx * 12.0, -gy * 12.0, np.ones_like(height)))
    normal /= np.linalg.norm(normal, axis=2, keepdims=True) + 1e-6
    shade = np.clip(np.sum(normal * light, axis=2), 0.0, 1.0)
    ambient = 0.48
    lit = colors * (ambient + shade[..., None] * 0.68)
    rim = np.clip(np.power(height, 2.8) * 34.0, 0.0, 34.0)
    lit += rim[..., None]
    return np.clip(lit, 0, 255)


def _blend_context_edges(image: Image.Image, neighbors: NeighborImages, context_px: int) -> Image.Image:
    if not neighbors or context_px <= 0:
        return image

    result = image.convert("RGB")
    width, height = result.size
    band = max(6, min(32, context_px // 4))
    result_np = np.asarray(result).astype(np.float32)

    if "left" in neighbors:
        edge = neighbors["left"].resize((width, height)).crop((width - band, 0, width, height))
        result_np[:, :band, :] = (
            np.asarray(edge).astype(np.float32) * np.linspace(0.75, 0.0, band)[None, :, None]
            + result_np[:, :band, :] * np.linspace(0.25, 1.0, band)[None, :, None]
        )
    if "right" in neighbors:
        edge = neighbors["right"].resize((width, height)).crop((0, 0, band, height))
        result_np[:, -band:, :] = (
            result_np[:, -band:, :] * np.linspace(1.0, 0.25, band)[None, :, None]
            + np.asarray(edge).astype(np.float32) * np.linspace(0.0, 0.75, band)[None, :, None]
        )
    if "top" in neighbors:
        edge = neighbors["top"].resize((width, height)).crop((0, height - band, width, height))
        result_np[:band, :, :] = (
            np.asarray(edge).astype(np.float32) * np.linspace(0.75, 0.0, band)[:, None, None]
            + result_np[:band, :, :] * np.linspace(0.25, 1.0, band)[:, None, None]
        )
    if "bottom" in neighbors:
        edge = neighbors["bottom"].resize((width, height)).crop((0, 0, width, band))
        result_np[-band:, :, :] = (
            result_np[-band:, :, :] * np.linspace(1.0, 0.25, band)[:, None, None]
            + np.asarray(edge).astype(np.float32) * np.linspace(0.0, 0.75, band)[:, None, None]
        )
    return Image.fromarray(np.uint8(np.clip(result_np, 0, 255)), "RGB")


class ProceduralTileGenerator:
    """Deterministic continuous terrain for local dev and automated tests."""

    def generate(self, ctx: TileGenerationContext) -> Image.Image:
        size = ctx.size
        base_seed = deterministic_tile_seed(0, 0, ctx.seed)
        local_seed = deterministic_tile_seed(ctx.x, ctx.y, ctx.seed)
        x0 = ctx.x * ctx.world_span_px
        y0 = ctx.y * ctx.world_span_px
        xs = np.linspace(x0, x0 + ctx.world_span_px, size, endpoint=False, dtype=np.float32)
        ys = np.linspace(y0, y0 + ctx.world_span_px, size, endpoint=False, dtype=np.float32)
        xx, yy = np.meshgrid(xs, ys)

        continent = _fractal_noise(xx, yy, base_seed)
        ridges = 1.0 - np.abs(_fractal_noise(xx * 1.18 + 1000.0, yy * 1.18 - 400.0, base_seed + 67) * 2.0 - 1.0)
        detail = _fractal_noise(xx * 2.7, yy * 2.7, local_seed + 17)
        height = np.clip(continent * 0.7 + ridges * ridges * 0.23 + detail * 0.11, 0.0, 1.0)
        colors = _apply_lighting(_colorize(height, detail, ctx.biome), height)

        rivers = _value_noise(xx + 5000.0, yy - 3000.0, 155.0, base_seed + 33)
        channels = np.exp(-np.square((rivers - 0.5) * 34.0))
        if ctx.biome in {"forest", "desert", "alien"}:
            water = np.array([37, 111, 128] if ctx.biome != "alien" else [54, 208, 188], dtype=np.float32)
            colors = colors * (1.0 - channels[..., None] * 0.36) + water * channels[..., None] * 0.36
        elif ctx.biome == "ocean":
            foam = (channels * 70.0 + np.maximum(0.0, height - 0.78) * 80.0)[..., None]
            colors += foam

        image = Image.fromarray(np.uint8(np.clip(colors, 0, 255)), "RGB")
        image = image.filter(ImageFilter.UnsharpMask(radius=1.15, percent=92, threshold=3))
        return _blend_context_edges(image, ctx.neighbors, ctx.context_px)
