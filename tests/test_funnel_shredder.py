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
    HATCH_CLOSED_X,
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
    shape.ebm_fill_color = (22, 114, 212, 255)
    shape.ebm_stroke_color = (12, 63, 143, 255)
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
    kinematics = [obj for obj in owned.values() if type(obj).__name__ == "Body" and obj.body_type == pymunk.Body.KINEMATIC]
    assert len(kinematics) == 3  # wheel + two airlock bolts
    wheel = [k for k in kinematics if abs(k.angular_velocity - 2.5) < 1e-9]
    assert len(wheel) == 1

    spoke_shapes = [
        obj for obj in owned.values()
        if type(obj).__name__ == "Segment" and obj.body is wheel[0]
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


def test_l0_ball_is_swallowed_by_the_box_and_exits_r0():
    space, registry, builder, tile = _world()
    body, shape = _ball(space, (16, 100), (200, 0))

    exited = False
    exit_angle = None
    for _ in range(900):
        _step(space, registry, builder, tile, 1)
        if body.position.x - BALL_RADIUS >= 400:
            exited = True
            vx, vy = body.velocity
            exit_angle = abs(math.degrees(math.atan2(vy, vx)))
            break

    assert exited, "ball never crossed R0"
    assert 255 <= body.position.y <= 345
    assert body.velocity.x > 0
    assert exit_angle <= 30, f"R0 exit angle {exit_angle}° exceeds the port cone"
    # Teleported, not shredded: no stockpile, no minis.
    assert not tile.stockpile
    assert not tile.minis
    # The tile never recolors the ball, and ownership is released at the edge.
    assert registry._balls.get(body) is None or registry._balls[body]["owner"] is None
    assert shape.ebm_fill_color == (22, 114, 212, 255)


def test_minis_rain_into_the_pipe_and_stay_contained():
    space, registry, builder, tile = _world()
    _drop_ball(space, registry, builder, tile)

    expected = MINI_COUNTS[0]
    assert len(tile.minis) == expected

    _step(space, registry, builder, tile, 480)  # 4 s to settle
    in_pipe = 0
    for body in tile.minis:
        x, y = body.position
        vx, vy = body.velocity
        assert MINI_RADIUS <= x <= 400 - MINI_RADIUS
        assert MINI_RADIUS <= y <= 400 - MINI_RADIUS
        assert vx * vx + vy * vy <= (MINI_MAX_SPEED + 600) ** 2
        if 165 <= x <= 235 and y > 195:
            in_pipe += 1
    # Most minis settle in the pipe on the closed lower bolt; the chamber
    # threshold is not reached, so no cycle starts.
    assert in_pipe >= expected - 1, f"only {in_pipe}/{expected} minis in the pipe"
    assert tile.phase == "fill"
    assert tile.top_open and not tile.bottom_open


def test_airlock_fuses_chamber_minis_into_b0_balls():
    space, registry, builder, tile = _world()
    fed = []
    exits = []
    upper_max = HATCH_CLOSED_X
    lower_min = HATCH_CLOSED_X
    for frame in range(120 * 40):  # up to 40 s
        if len(fed) < 5 and frame % 240 == 0:
            fed.append(_ball(space, (200, 16), (0, 140))[0])
        _step(space, registry, builder, tile, 1)
        upper_max = max(upper_max, tile.upper_hatch.position[0])
        lower_min = min(lower_min, tile.lower_hatch.position[0])
        for body in fed:
            if id(body) not in exits and not registry.ball_is_paused(body):
                if body.position.y - BALL_RADIUS >= 400:
                    exits.append(id(body))
                    x, _y = body.position
                    assert 155 <= x <= 245, f"B0 exit outside the aperture: {x}"
                    assert body.velocity.y > 0
    # Five balls in (~37 minis) drive several chamber cycles at 9 minis each;
    # every fused ball falls out through B0, and the bolts visibly slid out.
    assert len(exits) >= 3, f"exits: {len(exits)}"
    assert upper_max > 260 and lower_min < 140
    _step(space, registry, builder, tile, 240)
    assert tile.phase == "fill"
    # Conservation: every fed ball is either stockpiled or exited.
    assert len(tile.stockpile) + len(exits) == len(fed)
    assert not registry.runtime_errors


def test_fast_and_angled_t0_entries_are_shredded_and_contained():
    cases = [
        ((155, 20), (104, 591)),   # T0 left edge, 600 u/s at 10°
        ((245, 20), (-104, 591)),  # T0 right edge, mirrored
        ((200, 12), (0, 600)),     # T0 straight down, max speed
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


def test_fast_and_angled_l0_entries_teleport_to_r0():
    cases = [
        ((16, 55), (520, -300)),   # L0 high, fast upward angle
        ((16, 145), (520, 300)),   # L0 low, fast downward angle
        ((16, 100), (600, 0)),     # L0 straight fast
        ((16, 100), (1, 0)),       # L0 crawl: the floor drag delivers it
    ]
    for position, velocity in cases:
        space, registry, builder, tile = _world()
        body, _shape = _ball(space, position, velocity)
        exited = False
        for _ in range(3600):
            _step(space, registry, builder, tile, 1)
            if body.position.x - BALL_RADIUS >= 400:
                exited = True
                break
        assert exited, f"{position} {velocity} never exited R0"
        assert 255 <= body.position.y <= 345
        assert body.velocity.x > 0
        vx, vy = body.velocity
        assert abs(math.degrees(math.atan2(vy, vx))) <= 30
        assert not tile.stockpile and not tile.minis
        assert not registry.runtime_errors


def test_no_runtime_errors_across_a_busy_run():
    space, registry, builder, tile = _world()
    shredded = [
        _ball(space, (180, 15), (40, 500))[0],
        _ball(space, (220, 15), (-40, 500))[0],
    ]
    teleported = [_ball(space, (16, 80), (300, 100))[0]]
    for _ in range(3600):
        _step(space, registry, builder, tile, 1)
    for body in shredded:
        assert registry.ball_is_paused(body) or body.position.y - BALL_RADIUS >= 400
    assert all(body.position.x - BALL_RADIUS >= 400 for body in teleported)
    assert not registry.runtime_errors


def test_full_flow_validation_passes_with_the_airlock():
    from ebm.validator import validate_tile_flow
    result = validate_tile_flow(FunnelShredder, name="funnel shredder")
    assert result.ok, result.to_dict()
