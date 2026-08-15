from ebm.repeat_validation import validate_repeated_flow
from ebm.tiles.contributed.mirrored_s_switch import MirroredSSwitch
from ebm.validator import validate_tile_flow


def test_mirrored_s_switch_passes_single_and_repeat_validation():
    single = validate_tile_flow(MirroredSSwitch)
    assert single.ok, single.to_dict()
    assert single.output_counts == {"B0": 56, "R0": 57}
    repeat = validate_repeated_flow(MirroredSSwitch)
    assert repeat.ok, repeat.to_dict()


def test_mirrored_s_switch_has_unpowered_physical_rotor():
    source = __import__("inspect").getsource(MirroredSSwitch)
    assert "dynamic_body" in source
    assert "pivot" in source
    assert ".motor(" not in source
    assert "surface_velocity" not in source
