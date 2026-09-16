import inspect

import pytest

from ebm.ball_physics import INPUT_SPAWN_INTERVAL, TILE_SPAWN_INTERVAL
from ebm.engine import BOUNDARY_SPAWN_INTERVAL
from ebm.repeat_validation import validate_repeated_flow
from ebm.tile_catalog import default_tile
from ebm.validator import SPAWN_INTERVAL, validate_tile_flow


def test_all_source_defaults_share_point_eight_balls_per_second_tile_budget():
    assert TILE_SPAWN_INTERVAL == SPAWN_INTERVAL == 1.25
    assert INPUT_SPAWN_INTERVAL == BOUNDARY_SPAWN_INTERVAL == 2.5
    assert inspect.signature(validate_tile_flow).parameters['spawn_interval'].default == 1.25
    assert inspect.signature(validate_repeated_flow).parameters['spawn_interval'].default == 2.5


def test_single_validator_spawns_every_1_25_seconds_across_both_inputs():
    result = validate_tile_flow(default_tile, balls=8)
    assert result.ok, result.to_dict()
    arrivals = sorted(result.details, key=lambda item: item['id'])
    assert [item['spawned_at'] for item in arrivals] == pytest.approx([i * 1.25 for i in range(8)], abs=.01)
    assert [item['entry'] for item in arrivals] == ['T0', 'L0'] * 4


def test_repeat_validator_spawns_four_per_boundary_input_in_ten_seconds():
    result = validate_repeated_flow(default_tile, duration=10)
    assert not result.runtime_errors
    # Six open inputs around a 3x3 grid, each with its own initial phase.
    assert result.balls_spawned == 6 * 4


def test_explicit_validation_cadence_overrides_still_work():
    result = validate_tile_flow(default_tile, balls=8, spawn_interval=.4)
    arrivals = sorted(result.details, key=lambda item: item['id'])
    assert [item['spawned_at'] for item in arrivals] == pytest.approx([i * .4 for i in range(8)], abs=.01)
