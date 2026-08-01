from ebm.tile_catalog import default_tile
from ebm.validator import validate_tile_flow


def test_builtin_flow_tile_passes_concurrent_inventory_validation():
    result = validate_tile_flow(default_tile)
    assert result.ok, result.to_dict()
    assert result.balls_spawned == 120
    assert result.exited + result.active == 120
    assert result.all_outputs_used
