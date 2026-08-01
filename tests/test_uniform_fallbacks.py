from ebm.tile_catalog import default_tile
from ebm.validator import validate_tile_port_spec


def test_builtin_flow_tile_accepts_every_input_state_and_uses_all_outputs():
    result = validate_tile_port_spec(default_tile, duration=12)
    assert result.ok, result.to_dict()
    assert result.exited == 243
    assert result.all_outputs_used
