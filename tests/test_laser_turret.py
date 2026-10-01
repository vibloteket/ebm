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
from ebm.validator import validate_tile_flow
from ebm.tiles.contributed.laser_turret import (
    AIM_SECONDS,
    BLAST_RAYS,
    BOX_FADE_SECONDS,
    LaserTurret,
    NO_BEAM,
    NO_RAY,
    PIPE_CAPACITY,
    PIPE_TOP_SPAWN,
    PRIME_STOCK,
    RING_SEGMENTS,
    SENSOR_CENTER,
    SENSOR_RADIUS,
    TURRET,
)


def _world():
    space = pymunk.Space()
    space.gravity = (0, 1800)
    registry = TileResourceRegistry.for_space(space)
    builder = TileBuilder(registry, 1, (0, 0))
    tile = LaserTurret()
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
        space.step(dt)
        registry.advance(dt)


def _feed_kill(space, registry, builder, tile, x=160):
    """Drop one ball into the sensor and step until the turret destroys it."""
    body, _shape = _ball(space, (x, 50), (0, 500))
    for _ in range(150):
        _step(space, registry, builder, tile, 1)
        if registry.ball_is_paused(body):
            return body
    raise AssertionError("turret did not shoot the dropped ball")


def test_build_has_sensor_turret_and_hidden_effects():
    space, registry, builder, tile = _world()
    owned = {
        key: obj
        for key, obj in registry._objects.items()
        if registry._owner.get(key) == 1
    }
    sensors = [
        obj for obj in owned.values()
        if getattr(obj, "sensor", False)
    ]
    assert len(sensors) == 1
    sensor = sensors[0]
    assert type(sensor).__name__ == "Circle"
    assert sensor.radius == SENSOR_RADIUS
    assert tuple(sensor.offset) == SENSOR_CENTER

    bases = [
        obj for obj in owned.values()
        if type(obj).__name__ == "Circle" and not getattr(obj, "sensor", False)
    ]
    assert len(bases) == 2
    assert all(tuple(obj.body.position) == TURRET for obj in bases)

    visuals = [obj for obj in owned.values() if type(obj).__name__ == "VisualSegment"]
    assert len(visuals) == RING_SEGMENTS + 1 + 1 + BLAST_RAYS
    for visual in visuals:
        for x, y in (visual.a, visual.b):
            assert 0 <= x <= 400 and 0 <= y <= 400

    beam_style = registry._styles[tile.beam.id]
    assert beam_style.fill_color == NO_BEAM
    for ray in tile.rays:
        assert registry._styles[ray.id].fill_color == NO_RAY


def test_ball_inside_sensor_is_shot_and_explodes():
    space, registry, builder, tile = _world()
    body, _shape = _ball(space, (180, 40), (0, 200))

    fired_at = None
    for frame in range(240):
        _step(space, registry, builder, tile, 1)
        if registry.ball_is_paused(body):
            fired_at = frame
            break

    assert fired_at is not None
    # The visible aim delay must have elapsed before the shot.
    assert fired_at * (1 / 120) >= AIM_SECONDS
    # Beam and blast are visible right after the shot.
    assert tile.beam_t > 0
    assert tile.blast_t > 0
    beam = registry.resolve(1, tile.beam)
    assert beam.a != beam.b
    impact_x, impact_y = beam.b
    assert abs(impact_x - 180) < BALL_RADIUS
    assert math.hypot(impact_x - SENSOR_CENTER[0], impact_y - SENSOR_CENTER[1]) < SENSOR_RADIUS
    # The ring flashes on firing.
    assert tile.flash_t > 0

    # Effects fade and hide again.
    _step(space, registry, builder, tile, 120)
    assert registry._styles[tile.beam.id].fill_color == NO_BEAM
    assert registry._styles[tile.beam.id].stroke_color == NO_BEAM
    assert tile.blast_t == 0
    for ray in tile.rays:
        assert registry._styles[ray.id].fill_color == NO_RAY
    assert all(
        registry._styles[segment.id].fill_color[3] < 100 for segment in tile.ring
    )
    # The exploded ball stays owned by the tile, ready for a future respawn.
    assert registry._balls[body]["owner"] == 1


def test_fast_ball_crossing_the_zone_escapes_unshot():
    space, registry, builder, tile = _world()
    # A fast upward pass nicks the zone and leaves it before the aim delay.
    body, _shape = _ball(space, (200, 60), (300, -500))

    entered = left = False
    for _ in range(140):
        _step(space, registry, builder, tile, 1)
        distance = math.hypot(body.position.x - SENSOR_CENTER[0],
                              body.position.y - SENSOR_CENTER[1])
        entered = entered or distance <= SENSOR_RADIUS + BALL_RADIUS
        left = left or (entered and distance > SENSOR_RADIUS + BALL_RADIUS)
        if left or registry.ball_is_paused(body):
            break

    # The ball provably entered the sensor, was queued and dropped again on
    # the way out, and was never shot.
    assert entered and left
    assert not registry.ball_is_paused(body)
    assert tile.queue == []
    assert tile.target is None


def test_wave_primes_after_three_kills_and_spawns_both_outputs():
    space, registry, builder, tile = _world()
    _feed_kill(space, registry, builder, tile)
    _feed_kill(space, registry, builder, tile)
    assert len(tile.stockpile) == 2
    assert not tile.primed
    assert tile.box_ball is None
    assert not tile.pipe_balls and not tile.pending_spawn

    _feed_kill(space, registry, builder, tile)
    _step(space, registry, builder, tile, 3)
    assert tile.primed
    assert tile.box_ball is not None
    # The pipe half of the wave has materialized at the pipe top.
    pipe_handles = tile.pipe_balls or tile.pending_spawn
    assert len(pipe_handles) == 1
    _step(space, registry, builder, tile, 10)
    assert len(tile.pipe_balls) == 1
    ball = tile.pipe_balls[0]
    assert ball.position == PIPE_TOP_SPAWN or not ball.paused


def test_box_ball_fades_in_then_hatch_drops_it_out_b0():
    space, registry, builder, tile = _world()
    for _ in range(PRIME_STOCK):
        _feed_kill(space, registry, builder, tile)
    _step(space, registry, builder, tile, 3)
    ball = tile.box_ball
    assert ball is not None
    body = ball._body

    # Mid-fade: partially transparent, hatch still closed.
    _step(space, registry, builder, tile, int(BOX_FADE_SECONDS * 60))  # ~half fade
    alpha = body.shapes and next(iter(body.shapes)).ebm_fill_color[3]
    assert 40 < alpha < 220
    assert tile.hatch_open is False

    # Fade completes: hatch opens and the ball falls out through B0.
    while not tile.hatch_open:
        _step(space, registry, builder, tile, 1)
    assert tile.hatch.id in registry._paused_resources
    released = False
    for _ in range(240):
        _step(space, registry, builder, tile, 1)
        if registry._balls[body]["owner"] is None:
            released = True
            break
    assert released
    assert abs(body.position.x - 225) <= 45 + 1
    assert body.position.y > 400
    # The hatch closes again after its open window; the box is then ready for
    # the next wave.
    _step(space, registry, builder, tile, 60)
    assert tile.hatch_open is False
    assert tile.box_ball is None


def test_pipe_fills_then_shuttle_releases_one_ball_per_wave_through_r0():
    space, registry, builder, tile = _world()
    for _ in range(14):
        _feed_kill(space, registry, builder, tile)
        _step(space, registry, builder, tile, 24)

    exits = []
    for frame in range(1800):
        _step(space, registry, builder, tile, 1)
        for body in list(space.bodies):
            x, y = body.position
            if x > 400 and 240 < y < 360 and id(body) not in exits:
                vx, vy = body.velocity
                angle = math.degrees(math.atan2(vy, max(vx, 1e-9)))
                exits.append(id(body))
                assert 255 <= y <= 345
                assert 0 <= angle <= 30
        if len(tile.pipe_balls) >= PIPE_CAPACITY and exits:
            break
    assert exits, "shuttle never released a ball through R0"
    assert len(tile.pipe_balls) >= PIPE_CAPACITY - 1


def test_full_flow_validation_passes_with_recycling_spawners():
    result = validate_tile_flow(LaserTurret, name="laser turret")
    assert result.ok, result.to_dict()
