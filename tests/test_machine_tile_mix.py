from ebm.engine import Engine, MACHINE_TILE_IDS
from ebm.tile_catalog import active_tiles


def cleanup(engine):
    for ball in list(engine.balls):
        engine.remove_ball(ball)
    for active in list(engine.active_tiles.values()):
        engine.registry.destroy_owner(active.owner_id)


def test_machine_uses_stable_mix_of_contributed_tiles():
    engine = Engine(1200, 800)
    classes = {type(active.tile) for active in engine.active_tiles.values()}
    expected = {registration.tile_class for registration in active_tiles()}
    assert classes and classes <= expected
    assert MACHINE_TILE_IDS == tuple(registration.id for registration in active_tiles())
    modules = [registration.module for registration in active_tiles()]
    assert modules == sorted(modules)

    choices = {
        coord: type(active.tile)
        for coord, active in engine.active_tiles.items()
    }
    for coord, expected in choices.items():
        assert type(engine._tile_for_coord(*coord)) is expected
    cleanup(engine)
