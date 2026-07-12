from app.coords import (
    deterministic_tile_seed,
    predictive_tile_coords,
    visible_tile_coords,
    world_to_tile_coords,
)


def test_world_to_tile_coords_handles_negative_world_space() -> None:
    assert world_to_tile_coords(0, 0, 32) == (0, 0)
    assert world_to_tile_coords(31.99, -0.01, 32) == (0, -1)
    assert world_to_tile_coords(-32.1, 64.0, 32) == (-2, 2)


def test_visible_tiles_are_center_prioritized() -> None:
    coords = visible_tile_coords((10, -4), 1)
    assert coords[0] == (10, -4)
    assert set(coords) == {
        (9, -5),
        (10, -5),
        (11, -5),
        (9, -4),
        (10, -4),
        (11, -4),
        (9, -3),
        (10, -3),
        (11, -3),
    }


def test_predictive_tiles_follow_velocity_direction() -> None:
    coords = predictive_tile_coords((0, 0), (8.0, 1.0), radius=0, lead_tiles=3)
    assert coords == [(1, 0), (2, 0), (3, 0)]


def test_deterministic_tile_seed_is_stable_and_coordinate_sensitive() -> None:
    assert deterministic_tile_seed(1, 2, 3) == deterministic_tile_seed(1, 2, 3)
    assert deterministic_tile_seed(1, 2, 3) != deterministic_tile_seed(2, 1, 3)

