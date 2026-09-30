"""Per-tile-type update() profiling, opt-in via Engine.set_tile_profiling."""

from ebm.engine import Engine
from ebm.tile_base import TileBase, tile_has_frame_update
from ebm.tiles.contributed.conveyor_lift import ConveyorLift


def test_tile_profiling_off_by_default():
    engine = Engine(1280, 800)
    engine.seed_initial_balls()
    for _ in range(30):
        engine.step_frame(1 / 60)
    assert engine.consume_tile_profile() == {}


def test_tile_profiling_collects_per_type_timings():
    engine = Engine(1280, 800)
    engine.seed_initial_balls()
    engine.set_tile_profiling(True)
    frames = 30
    for _ in range(frames):
        engine.step_frame(1 / 60)
    profile = engine.consume_tile_profile()

    assert profile, "expected per-tile timings while profiling is enabled"
    updatable = [type(engine.active_tiles[c].tile).__name__ for c in engine._updatable_coords]
    assert sorted(profile) == sorted(set(updatable))
    for name, bucket in profile.items():
        assert bucket["total_ms"] > 0
        assert bucket["max_ms"] > 0
        expected_calls = updatable.count(name) * frames
        assert bucket["calls"] == expected_calls


def test_enabling_starts_a_fresh_window_and_disable_clears():
    engine = Engine(1280, 800)
    engine.seed_initial_balls()
    engine.set_tile_profiling(True)
    engine.step_frame(1 / 60)
    engine.set_tile_profiling(True)  # re-enable: reset
    assert engine.consume_tile_profile() == {}
    engine.step_frame(1 / 60)
    assert engine.consume_tile_profile(), "expected one fresh frame of data"
    engine.set_tile_profiling(False)
    for _ in range(5):
        engine.step_frame(1 / 60)
    assert engine.consume_tile_profile() == {}


def test_only_real_update_overrides_are_updatable():
    engine = Engine(1280, 800)
    for coord, active in engine.active_tiles.items():
        assert tile_has_frame_update(active.tile) == (coord in engine._updatable_coords)
    # Panning re-reconciles; the set must stay consistent with active tiles.
    engine.pan(1200, 800)
    for coord, active in engine.active_tiles.items():
        assert tile_has_frame_update(active.tile) == (coord in engine._updatable_coords)
    assert engine._updatable_coords <= set(engine.active_tiles)


def test_conveyor_lift_counts_as_updatable_and_profiles():
    engine = Engine(1280, 800)
    engine.set_tile_profiling(True)
    for _ in range(10):
        engine.step_frame(1 / 60)
    profile = engine.consume_tile_profile()
    if any(isinstance(a.tile, ConveyorLift) for a in engine.active_tiles.values()):
        assert ConveyorLift.__name__ in profile
