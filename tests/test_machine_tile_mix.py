from ebm.engine import Engine, MACHINE_TILE_IDS
from ebm.tiles.contributed.segment_switchback import SegmentSwitchback
from ebm.tiles.contributed.teleport_collector import TeleportCollector


def cleanup(engine):
    for ball in list(engine.balls):
        engine.remove_ball(ball)
    for active in list(engine.active_tiles.values()):
        engine.registry.destroy_owner(active.owner_id)


def test_machine_uses_stable_mix_of_contributed_tiles():
    engine = Engine(1200, 800)
    classes = {type(active.tile) for active in engine.active_tiles.values()}
    assert classes == {SegmentSwitchback, TeleportCollector}
    assert MACHINE_TILE_IDS == (
        "contributed.segment-switchback",
        "contributed.teleport-collector",
    )

    choices = {
        coord: type(active.tile)
        for coord, active in engine.active_tiles.items()
    }
    for coord, expected in choices.items():
        assert type(engine._tile_for_coord(*coord)) is expected
    cleanup(engine)
