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
from ebm.tiles.contributed.water_pool import (
    B0_HATCH_Y,
    B0_SPAWN,
    CAPTURE_BOTTOM,
    POOL_FLOOR,
    R0_GATE_X,
    R0_SPAWN,
    WATER_TOP,
    WaterPool,
)


def _world():
    space = pymunk.Space()
    space.gravity = (0, 1800)
    registry = TileResourceRegistry.for_space(space)
    builder = TileBuilder(registry, 1, (0, 0))
    tile = WaterPool()
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


def _run_until(space, registry, builder, tile, predicate, seconds=10.0):
    frames = int(seconds * 120)
    for _ in range(frames):
        _step(space, registry, builder, tile, 1)
        if predicate():
            return True
    return False


def _count_exits(space, bottom=None, right=None):
    """Count live balls past each output edge (outside the tile)."""
    b = r = 0
    for body in space.bodies:
        if len(body.shapes) != 1 or not isinstance(next(iter(body.shapes)), pymunk.Circle):
            continue
        x, y = body.position
        if x > 400 + BALL_RADIUS:
            r += 1
        elif y > 400 + BALL_RADIUS:
            b += 1
    if bottom is not None:
        assert b == bottom
    if right is not None:
        assert r == right
    return b, r


def _captured(tile):
    """Balls dissolved into the pool: stockpiled or mid-cycle in a box."""
    in_boxes = sum(box["ball"] is not None for box in tile.boxes.values())
    return len(tile.stockpile) + in_boxes


def test_t0_ball_sinks_fades_and_is_stockpiled():
    space, registry, builder, tile = _world()
    body, _ = _ball(space, (200, 20), (0, 300))
    assert _run_until(space, registry, builder, tile,
                      lambda: registry.ball_is_paused(body), seconds=5)
    assert _captured(tile) == 1
    assert not tile.sinking


def test_l0_slow_ball_rolls_in_and_dissolves():
    space, registry, builder, tile = _world()
    # Weakest plausible L0 entry: nearly stationary at the port band bottom.
    body, _ = _ball(space, (20, 140), (80, 0))
    assert _run_until(space, registry, builder, tile,
                      lambda: registry.ball_is_paused(body), seconds=5)
    assert _captured(tile) == 1


def test_fast_l0_ball_cannot_clear_the_pool():
    space, registry, builder, tile = _world()
    # Hardest case: 600 u/s at the top of the L0 band, angled up 30°.
    body, _ = _ball(space, (20, 55), (520, -300))
    assert _run_until(space, registry, builder, tile,
                      lambda: registry.ball_is_paused(body), seconds=8)
    assert body.position.x < 400 - BALL_RADIUS or registry.ball_is_paused(body)


def test_boxes_alternate_and_conserve_balls():
    space, registry, builder, tile = _world()
    for i in range(4):
        _ball(space, (200, 20), (0, 300))
        _step(space, registry, builder, tile, 150)  # 1.25 s supply cadence
    ok = _run_until(
        space, registry, builder, tile,
        lambda: _try(lambda: _count_exits(space, bottom=2, right=2))
        and all(box["phase"] == "idle" for box in tile.boxes.values()),
        seconds=30,
    )
    phases = [box["phase"] for box in tile.boxes.values()]
    assert ok, f"expected 2 B0 + 2 R0 exits and idle boxes, got {_count_exits(space)} and phases {phases}"
    assert not tile.stockpile


def _try(fn):
    try:
        fn()
        return True
    except AssertionError:
        return False


def test_full_flow_validation_passes():
    from ebm.validator import validate_tile_flow

    result = validate_tile_flow(WaterPool, name="water pool")
    assert result.ok, result.to_dict()
    assert result.output_counts["B0"] > 0
    assert result.output_counts["R0"] > 0
    assert abs(result.output_counts["B0"] - result.output_counts["R0"]) <= 1


def test_b0_ball_condenses_inside_crate_and_drops():
    space, registry, builder, tile = _world()
    body, _ = _ball(space, (200, 20), (0, 300))
    assert _run_until(space, registry, builder, tile,
                      lambda: tile.boxes["b0"]["phase"] == "condense", seconds=6)
    x, y = body.position
    assert abs(x - B0_SPAWN[0]) < 30 and abs(y - B0_SPAWN[1]) < 30
    # After release the ball must leave through the B0 band moving down.
    assert _run_until(space, registry, builder, tile,
                      lambda: body.position.y > 400 + BALL_RADIUS, seconds=4)
    assert abs(body.position.x - 200) < 60


def test_r0_ball_exits_right_within_the_band():
    space, registry, builder, tile = _world()
    first, _ = _ball(space, (200, 20), (0, 300))
    _step(space, registry, builder, tile, 150)
    second, _ = _ball(space, (200, 20), (0, 300))
    # Second ball is routed to the R0 box.
    assert _run_until(space, registry, builder, tile,
                      lambda: tile.boxes["r0"]["phase"] == "condense", seconds=8)
    assert _run_until(space, registry, builder, tile,
                      lambda: second.position.x > 400 + BALL_RADIUS, seconds=6)
    y = second.position[1]
    assert 255 <= y <= 345, f"R0 exit y={y} outside the band"
    vx, vy = second.velocity
    assert vx > 0 and abs(vy) <= vx * 0.5774 + 1e-6, "exit angle exceeds 30°"
