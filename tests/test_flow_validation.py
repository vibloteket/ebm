from ebm import TileBase
from ebm.tile_catalog import default_tile
from ebm.validator import MAX_ACTIVE_BALLS, VALIDATION_BALLS, validate_tile_flow


class BucketTile(TileBase):
    id = "test.bucket"
    title = "Bucket"
    author = "Tests"
    api_version = 1

    def build(self, builder):
        # A closed physical box keeps all balls alive and inside forever.
        builder.static_segment((0, 0), (400, 0), 4)
        builder.static_segment((400, 0), (400, 400), 4)
        builder.static_segment((400, 400), (0, 400), 4)
        builder.static_segment((0, 400), (0, 0), 4)


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
