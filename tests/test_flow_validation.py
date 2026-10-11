from ebm import TileBase
from ebm.tile_catalog import default_tile
from ebm.validator import MAX_ACTIVE_BALLS, VALIDATION_BALLS, ValidationResult, validate_tile_flow


class BucketTile(TileBase):
    author = "Tests"

    def build(self, builder):
        # A closed physical box keeps all balls alive and inside forever.
        builder.static_segment((4, 4), (396, 4), 4)
        builder.static_segment((396, 4), (396, 396), 4)
        builder.static_segment((396, 396), (4, 396), 4)
        builder.static_segment((4, 396), (4, 4), 4)


def test_flow_validator_uses_global_inventory_contract():
    result = validate_tile_flow(default_tile)
    assert result.balls_spawned == VALIDATION_BALLS
    assert result.exited + result.active == VALIDATION_BALLS
    assert result.peak_active <= MAX_ACTIVE_BALLS
    assert result.invalid == result.lost == 0
    assert result.ok, result.to_dict()


def test_tile_that_accumulates_balls_exceeds_global_capacity():
    result = validate_tile_flow(BucketTile, balls=12, max_active=5, spawn_interval=.05)
    assert result.active > 5
    assert result.peak_active > 5
    assert result.capacity_exceeded
    assert not result.ok


class OneSidedTile(TileBase):
    author = "Tests"

    def build(self, builder):
        # Every ball slides down one ramp and out the B0 aperture.
        builder.static_segment((3, 150), (165, 392), 3, friction=0, elasticity=0)
        builder.static_segment((3, 30), (115, 30), 3, friction=0, elasticity=0)


def test_one_sided_tile_fails_the_output_share_gate():
    result = validate_tile_flow(OneSidedTile)
    assert result.exited > 10
    assert result.output_counts["R0"] == 0
    assert not result.balanced_outputs
    assert not result.ok, result.to_dict()


def test_output_share_gate_band_and_small_sample_floor():
    def make(exited, b0, r0, share=.4):
        return ValidationResult(
            "unit", exited, 5, min_output_share=share,
            balls_spawned=exited, exited=exited,
            output_counts={"B0": b0, "R0": r0})

    assert not make(10, 7, 3).balanced_outputs  # 70/30 breaks the 40/60 band
    assert make(10, 6, 4).balanced_outputs      # 60/40 is the edge, still ok
    assert make(5, 5, 0).balanced_outputs       # too few exits to judge the split


def test_output_share_gate_is_disabled_with_min_output_share_zero():
    result = validate_tile_flow(OneSidedTile, min_output_share=0)
    assert result.balanced_outputs
