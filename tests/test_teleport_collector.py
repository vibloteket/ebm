import pymunk
import pytest

from ebm.ball_physics import configure_ball_body
from ebm.ports import BALL_RADIUS, TILE_SIZE, tile_origin
from ebm.tile_api import (
    BALL_COLLISION_TYPE,
    BALL_ELASTICITY,
    BALL_FRICTION,
    TileBuilder,
    TileResourceRegistry,
    ball_shape_filter,
)
from ebm.tiles.contributed.teleport_collector import BOX, MAGIC, MAGIC_OFF, TeleportCollector


def test_neighbor_handoff_reaches_teleport_sensor_after_previous_owner_releases():
    """Reproduce R0 -> L0 handoff used by the 3x3 repeated preview."""
    space = pymunk.Space()
    space.gravity = (0, 1800)
    registry = TileResourceRegistry.for_space(space)

    left_origin = tile_origin(0, 0)
    right_origin = tile_origin(0, 1)
    left = TileBuilder(registry, 1, left_origin)
    right = TileBuilder(registry, 2, right_origin)
    TeleportCollector().build(left)
    TeleportCollector().build(right)

    body = pymunk.Body(1, pymunk.moment_for_circle(1, 0, BALL_RADIUS))
    configure_ball_body(body)
    body.position = (left_origin[0] + TILE_SIZE - 20, left_origin[1] + 300)
    body.velocity = (300, 0)
    shape = pymunk.Circle(body, BALL_RADIUS)
    shape.friction = BALL_FRICTION
    shape.elasticity = BALL_ELASTICITY
    shape.collision_type = BALL_COLLISION_TYPE
    shape.filter = ball_shape_filter()
    space.add(body, shape)

    # Simulate ownership by the left tile before the ball crosses the edge.
    registry._claim_ball(1, body, shape)
    teleported = False
    for _ in range(180):
        space.step(1 / 120)
        registry.advance(1 / 120)
        x, y = body.position
        if right_origin[0] + 260 < x < right_origin[0] + 340 and right_origin[1] + 230 < y < right_origin[1] + 320:
            teleported = True
            break

    assert teleported
    assert registry._balls[body]["owner"] == 2


def test_teleport_flashes_portal_wall_and_translucent_beam():
    space = pymunk.Space()
    registry = TileResourceRegistry.for_space(space)
    builder = TileBuilder(registry, 1, (0, 0))
    tile = TeleportCollector()
    tile.build(builder)

    portal_style = registry._styles[tile.portal.id]
    beam_style = registry._styles[tile.beam.id]
    assert portal_style.fill_color == BOX
    assert beam_style.fill_color == MAGIC_OFF
    assert MAGIC[3] < 255

    body = pymunk.Body(1, pymunk.moment_for_circle(1, 0, BALL_RADIUS))
    configure_ball_body(body)
    body.position = (50, 100)
    body.velocity = (100, 0)
    shape = pymunk.Circle(body, BALL_RADIUS)
    shape.collision_type = BALL_COLLISION_TYPE
    shape.filter = ball_shape_filter()
    space.add(body, shape)
    for _ in range(10):
        space.step(1 / 120)
        registry.advance(1 / 120)

    assert portal_style.fill_color == MAGIC
    assert beam_style.fill_color == MAGIC
    beam = registry.resolve(1, tile.beam)
    assert beam.a[0] == pytest.approx(50, abs=20)
    assert beam.a[1] == pytest.approx(100, abs=25)
    assert beam.b == (300.0, 275.0)
    tile.update(builder, 0.3)
    assert portal_style.fill_color == BOX
    assert beam_style.fill_color == MAGIC_OFF
