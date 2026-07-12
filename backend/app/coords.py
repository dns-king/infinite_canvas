from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable


TileCoord = tuple[int, int]


def world_to_tile_coords(camera_x: float, camera_z: float, tile_world_size: float) -> TileCoord:
    if tile_world_size <= 0:
        raise ValueError("tile_world_size must be positive")
    return math.floor(camera_x / tile_world_size), math.floor(camera_z / tile_world_size)


def visible_tile_coords(center: TileCoord, radius: int) -> list[TileCoord]:
    cx, cy = center
    coords: list[TileCoord] = []
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            coords.append((x, y))
    coords.sort(key=lambda p: (abs(p[0] - cx) + abs(p[1] - cy), p[1], p[0]))
    return coords


def predictive_tile_coords(
    center: TileCoord,
    velocity: tuple[float, float],
    radius: int,
    lead_tiles: int,
) -> list[TileCoord]:
    vx, vz = velocity
    mag = math.hypot(vx, vz)
    if mag < 0.001:
        return []

    step_x = int(round(vx / mag))
    step_y = int(round(vz / mag))
    if step_x == 0 and step_y == 0:
        return []

    predicted: list[TileCoord] = []
    seen: set[TileCoord] = set()
    for lead in range(1, lead_tiles + 1):
        ahead = (center[0] + step_x * lead, center[1] + step_y * lead)
        for coord in visible_tile_coords(ahead, radius):
            if coord not in seen:
                seen.add(coord)
                predicted.append(coord)
    return predicted


def deterministic_tile_seed(x: int, y: int, global_seed: int) -> int:
    digest = hashlib.blake2b(f"{global_seed}:{x}:{y}".encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "little") & 0x7FFFFFFF


def manhattan_priority(center: TileCoord, coords: Iterable[TileCoord]) -> list[tuple[float, TileCoord]]:
    cx, cy = center
    return [(float(abs(x - cx) + abs(y - cy)), (x, y)) for x, y in coords]

