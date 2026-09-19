import ast
import inspect

import pytest

from ebm.ports import Port
from ebm.repeat_validation import validate_repeated_flow
from ebm.tiles.contributed.conveyor_lift import BELT_SPEED, ConveyorLift
from ebm.validator import validate_tile_flow


@pytest.mark.parametrize("dt", [1 / 120, 1 / 60])
def test_conveyor_lift_passes_full_single_tile_flow(dt):
    result = validate_tile_flow(ConveyorLift, dt=dt)
    assert result.ok, result.to_dict()
    assert result.output_counts[Port.B0.name] > 0
    assert result.output_counts[Port.R0.name] > 0


def test_conveyor_lift_passes_repeated_flow():
    result = validate_repeated_flow(ConveyorLift)
    assert result.ok, result.to_dict()


def test_only_conveyor_mechanism_is_actively_driven():
    source = inspect.getsource(ConveyorLift)
    tree = ast.parse(source)
    calls = [node.func for node in ast.walk(tree) if isinstance(node, ast.Call)]
    forbidden = {
        "set_ball_position", "set_ball_velocity", "pause_ball", "resume_ball",
        "apply_force", "apply_impulse", "apply_torque", "motor",
    }
    assert not any(isinstance(func, ast.Attribute) and func.attr in forbidden for func in calls)
    assert "kinematic_body" in source
    assert "segment_shape" in source
    assert BELT_SPEED > 0
