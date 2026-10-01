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
from ebm.tiles.contributed.laser_turret import (
    AIM_SECONDS,
    BLAST_RAYS,
    LaserTurret,
    NO_BEAM,
    NO_RAY,
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
    assert SENSOR_CENTER[1] < impact_y < SENSOR_CENTER[1] + SENSOR_RADIUS
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

    min_distance = math.inf
    for _ in range(140):
        _step(space, registry, builder, tile, 1)
        min_distance = min(
            min_distance,
            math.hypot(body.position.x - 180, body.position.y - 180),
        )

    # The ball provably entered the sensor (touch distance is radius + ball),
    # was queued and dropped again, and was never shot.
    assert min_distance <= SENSOR_RADIUS + BALL_RADIUS
    assert not registry.ball_is_paused(body)
    assert tile.queue == []
    assert tile.target is None
    assert body.position.x > 400
