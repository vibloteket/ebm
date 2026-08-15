from ebm.tile_catalog import create_tile, default_tile
from ebm.validator import validate_tile_flow


def test_builtin_flow_tile_passes_concurrent_inventory_validation():
    result = validate_tile_flow(default_tile)
    assert result.ok, result.to_dict()
    assert result.balls_spawned == 120
    assert result.exited + result.active == 120
    assert result.all_outputs_used


def test_teleport_collector_passes_with_expected_routes():
    tile = create_tile("contributed.teleport-collector")
    result = validate_tile_flow(lambda: tile)
    assert result.ok, result.to_dict()
    assert {
        (detail["entry"], detail["exit"])
        for detail in result.details
        if detail["status"] == "exited"
    } == {("T0", "B0"), ("L0", "R0")}


def test_segment_switchback_passes_without_surface_velocity():
    registration = create_tile("contributed.segment-switchback")
    result = validate_tile_flow(lambda: registration)
    assert result.ok, result.to_dict()

    from ebm.tiles.contributed.segment_switchback import RAIL_ELASTICITY, SegmentSwitchback
    import inspect

    assert "surface_velocity" not in inspect.getsource(SegmentSwitchback.build)
    assert RAIL_ELASTICITY == 0.45
