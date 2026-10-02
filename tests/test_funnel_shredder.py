import math

import pymunk

from ebm.ball_physics import configure_ball_body
from ebm.ports import BALL_RADIUS
from ebm.tile_api import (
    BALL_COLLISION_TYPE,
    BALL_ELASTICITY,
    BALL_FRICTION,
    TileBuilder,
    TileResourceRegistry,
    ball_shape_filter,
)
from ebm.tiles.contributed.funnel_shredder import (
    BLAST_RAYS,
    FunnelShredder,
    MAX_MINIS,
    MINI_COUNTS,
    MINI_MAX_SPEED,
    MINI_RADIUS,
    NO_RAY,
    SPOKES,
    SPOKE_FILL,
    SPOKE_FLASH,
    WHEEL,
)


def _world():
    space = pymunk.Space()
    space.gravity = (0, 1800)
    registry = TileResourceRegistry.for_space(space)
    builder = TileBuilder(registry, 1, (0, 0))
    tile = FunnelShredder()
    tile.build(builder)
    return space, registry, builder, tile


def _ball(space, position, velocity):
    body = pymunk.Body(1, pymunk.moment_for_circle(1, 0, BALL_RADIUS))
    configure_ball_body(body)
    body.position = position
    body.velocity = velocity
    shape = pymunk.Circle(body, BALL_RADIUS)
    shape.friction = BALL_FRICTION
    shape.elasticity = BALL_ELASTICITY
    shape.collision_type = BALL_COLLISION_TYPE
    shape.filter = ball_shape_filter()
    space.add(body, shape)
    return body, shape


def _step(space, registry, builder, tile, frames, dt=1 / 120):
    for _ in range(frames):
        tile.update(builder, dt)
        registry.validate_geometry(time=0, phase="update")
        space.step(dt)
        registry.validate_geometry(time=dt, phase="physics")
        registry.advance(dt)


def _drop_ball(space, registry, builder, tile, position=(200, 20), velocity=(0, 300), frames=480):
    """Drop one ball and step until the wheel shreds it."""
    body, _shape = _ball(space, position, velocity)
    for _ in range(frames):
        _step(space, registry, builder, tile, 1)
        if registry.ball_is_paused(body):
            return body
    raise AssertionError(f"ball at {position} was never shredded")


def test_build_layout_pool_and_hidden_effects():
    space, registry, builder, tile = _world()
    owned = {
        key: obj
        for key, obj in registry._objects.items()
        if registry._owner.get(key) == 1
    }
    wheels = [obj for obj in owned.values() if type(obj).__name__ == "Body" and obj.body_type == pymunk.Body.KINEMATIC]
    assert len(wheels) == 1
    assert abs(wheels[0].angular_velocity - 2.5) < 1e-9

    spoke_shapes = [
        obj for obj in owned.values()
        if type(obj).__name__ == "Segment" and obj.body is wheels[0]
    ]
    assert len(spoke_shapes) == SPOKES

    # The whole mini pool exists from build, paused and therefore invisible.
    assert len(tile.mini_pool) == MAX_MINIS
    assert not tile.minis
    assert all(body.id in registry._paused_resources for body in tile.mini_pool)
    minis = [
        obj for obj in owned.values()
        if type(obj).__name__ == "Circle" and not getattr(obj, "sensor", False)
        and abs(obj.radius - MINI_RADIUS) < 1e-9
    ]
    assert len(minis) == MAX_MINIS

    visuals = [obj for obj in owned.values() if type(obj).__name__ == "VisualSegment"]
    assert len(visuals) == BLAST_RAYS
    for ray in tile.rays:
        assert registry._styles[ray.id].fill_color == NO_RAY
    registry.validate_geometry(time=0, phase="build")


def test_t0_ball_is_shredded_into_minis():
    space, registry, builder, tile = _world()
    body, _shape = _ball(space, (200, 20), (0, 300))

    fired_at = None
    for frame in range(480):
        _step(space, registry, builder, tile, 1)
        if registry.ball_is_paused(body):
            fired_at = frame
            break

    assert fired_at is not None
    assert len(tile.minis) == MINI_COUNTS[0]
    assert len(tile.stockpile) == 1
    assert registry._balls[body]["owner"] == 1
    # The blast flash fired and the spokes flashed.
    assert tile.blast_t > 0
    assert tile.flash_t > 0
    assert registry._styles[tile.spokes[0].id].fill_color == SPOKE_FLASH

    # Effects decay back to rest.
    _step(space, registry, builder, tile, 120)
    assert tile.blast_t == 0
    assert tile.flash_t == 0
    for ray in tile.rays:
        assert registry._styles[ray.id].fill_color == NO_RAY
    assert registry._styles[tile.spokes[0].id].fill_color == SPOKE_FILL


def test_l0_ball_slides_down_the_wall_into_the_wheel():
    space, registry, builder, tile = _world()
    _drop_ball(space, registry, builder, tile, position=(16, 100), velocity=(180, 0))
    assert len(tile.stockpile) == 1
    assert len(tile.minis) == MINI_COUNTS[0]


def test_minis_rain_into_the_tray_and_stay_contained():
    space, registry, builder, tile = _world()
    for _ in range(3):
        _drop_ball(space, registry, builder, tile)
        _step(space, registry, builder, tile, 60)

    expected = sum(MINI_COUNTS[:3])
    assert len(tile.minis) == expected

    _step(space, registry, builder, tile, 720)  # 6 s to settle
    tray = 0
    for body in tile.minis:
        x, y = body.position
        vx, vy = body.velocity
        assert MINI_RADIUS <= x <= 400 - MINI_RADIUS
        assert MINI_RADIUS <= y <= 400 - MINI_RADIUS
        assert vx * vx + vy * vy <= (MINI_MAX_SPEED + 600) ** 2
        if 110 <= x <= 290 and y > 265:
            tray += 1
    # Most minis settle in the tray; a few strays may rest on the side gutters.
    assert tray >= expected * 0.6, f"only {tray}/{expected} minis in the tray"


def test_pool_recycles_calm_tray_minis_when_exhausted():
    space, registry, builder, tile = _world()
    total = 0
    drops = 11  # Cycled counts: 6+7+8+9+7+6+8+5+6+7+8 = 77 minis > MAX_MINIS
    for _ in range(drops):
        _drop_ball(space, registry, builder, tile)
        _step(space, registry, builder, tile, 90)
        total += 1

    expected_minis = sum(MINI_COUNTS[i % len(MINI_COUNTS)] for i in range(drops))
    assert expected_minis > MAX_MINIS
    assert len(tile.minis) == MAX_MINIS
    assert not tile.mini_pool
    assert len(tile.stockpile) == total
    _step(space, registry, builder, tile, 480)
    assert len(tile.minis) == MAX_MINIS
    assert not registry.runtime_errors


def test_fast_and_angled_entries_are_shredded_and_contained():
    cases = [
        ((155, 20), (104, 591)),   # T0 left edge, 600 u/s at 10°
        ((245, 20), (-104, 591)),  # T0 right edge, mirrored
        ((16, 55), (520, -300)),   # L0 high, fast upward angle
        ((16, 145), (520, 300)),   # L0 low, fast downward angle
        ((16, 100), (600, 0)),     # L0 straight fast
    ]
    for position, velocity in cases:
        space, registry, builder, tile = _world()
        _drop_ball(space, registry, builder, tile, position=position, velocity=velocity, frames=900)
        assert len(tile.stockpile) == 1, f"{position} {velocity}"
        _step(space, registry, builder, tile, 360)
        for body in tile.minis:
            x, y = body.position
            assert MINI_RADIUS <= x <= 400 - MINI_RADIUS
            assert MINI_RADIUS <= y <= 400 - MINI_RADIUS
        assert not registry.runtime_errors


def test_no_runtime_errors_across_a_busy_run():
    space, registry, builder, tile = _world()
    bodies = [
        _ball(space, (180, 15), (40, 500))[0],
        _ball(space, (220, 15), (-40, 500))[0],
        _ball(space, (16, 80), (300, 100))[0],
    ]
    for _ in range(1200):
        _step(space, registry, builder, tile, 1)
    assert all(registry.ball_is_paused(body) for body in bodies)
    assert not registry.runtime_errors
