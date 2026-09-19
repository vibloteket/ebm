import math

import pymunk
import pytest

from ebm.tile_api import BALL_COLLISION_TYPE, TileBuilder, TileResourceRegistry


def world():
    space = pymunk.Space()
    registry = TileResourceRegistry.for_space(space)
    b = TileBuilder(registry, 1, (0, 0))
    body = b.dynamic_body((200, 140))
    b.circle_shape(body, (0, 0), 10, density=.01)
    return space, registry, b, body


def test_spring_sags_further_under_load_and_rope_allows_slack():
    space, registry, b, body = world()
    space.gravity = (0, 1800)
    spring = b.spring(body, (200, 20), (0, 0), rest_length=100, stiffness=1000, damping=150)
    rope = b.rope(body, (200, 20), (0, 0), max_length=120)
    assert isinstance(registry.resolve(1, spring), pymunk.DampedSpring)
    assert isinstance(registry.resolve(1, rope), pymunk.SlideJoint)
    for _ in range(960):
        space.step(1 / 120)
    before = body.position[1]
    assert before == pytest.approx(120 + math.pi * 1800 / 1000, abs=.05)
    b.circle_shape(body, (0, 0), 5, density=.02)
    for _ in range(960):
        space.step(1 / 120)
    assert body.position[1] - before == pytest.approx(math.pi * .5 * 1800 / 1000, abs=.05)
    registry.validate_geometry()


def test_rope_has_no_compression_force_and_limits_extension():
    space, registry, b, body = world()
    space.gravity = (0, 1800)
    body.set_position((200, 80))
    b.rope(body, (200, 20), (0, 0), max_length=100)
    space.step(1 / 120)
    assert body.velocity[1] == pytest.approx(15)
    for _ in range(600):
        space.step(1 / 120)
    assert body.position[1] == pytest.approx(120, abs=.1)


def test_rope_drawing_and_attached_sensor_do_not_collide_or_add_mass():
    space, registry, b, body = world()
    body.set_position((200, 240))
    raw = registry.resolve(1, body)
    mass, moment = raw.mass, raw.moment
    b.spring(body, (200, 20), (0, 0), rest_length=220, stiffness=100, damping=10)
    b.rope(body, (200, 20), (0, 0), max_length=240)
    b.visual_segment((200, 20), (200, 240), 2)
    sensor = b.sensor_polygon(body, ((-10, -160), (10, -160), (10, -140), (-10, -140)))
    assert (raw.mass, raw.moment) == pytest.approx((mass, moment))
    assert registry.resolve(1, sensor).sensor
    assert registry.resolve(1, sensor).mass == 0
    contacts = []
    b.on_ball_contact(sensor, begin=lambda event: contacts.append(event.ball))
    ball = pymunk.Body(1, 1)
    ball.position = (180, 90)
    ball.velocity = (120, 0)
    shape = pymunk.Circle(ball, 5)
    shape.collision_type = BALL_COLLISION_TYPE
    space.add(ball, shape)
    for _ in range(48):
        space.step(1 / 120)
    assert ball.position == pytest.approx((228, 90))
    assert ball.velocity == pytest.approx((120, 0))
    assert contacts
    assert len(space.shapes) == 3  # Body circle, massless sensor, test ball; no rope collider.


def test_suspension_and_sensor_follow_body_pause_resume_and_cleanup():
    space, registry, b, body = world()
    b.spring(body, (200, 20), (0, 0), rest_length=120, stiffness=100, damping=10)
    b.rope(body, (200, 20), (0, 0), max_length=140)
    b.sensor_polygon(body, ((-20, -20), (20, -20), (20, 20), (-20, 20)))
    body.pause()
    assert not space.shapes and not space.constraints and not space.bodies
    body.resume()
    assert len(space.shapes) == 2 and len(space.constraints) == 2 and len(space.bodies) == 1
    registry.destroy_owner(1)
    assert not space.shapes and not space.constraints and not space.bodies


@pytest.mark.parametrize('value', [-1, float('nan'), float('inf')])
def test_invalid_suspension_parameters_do_not_register_constraints(value):
    space, registry, b, body = world()
    for key in ('rest_length', 'stiffness', 'damping'):
        kwargs = dict(rest_length=120, stiffness=100, damping=10)
        kwargs[key] = value
        with pytest.raises(ValueError):
            b.spring(body, (200, 20), (0, 0), **kwargs)
    with pytest.raises(ValueError):
        b.rope(body, (200, 20), (0, 0), max_length=value)
    assert not space.constraints


def test_cross_owner_suspension_and_sensor_are_rejected():
    space, registry, b, body = world()
    other = TileBuilder(registry, 2, (400, 200))
    with pytest.raises(PermissionError):
        other.spring(body, (200, 20), (0, 0), rest_length=120, stiffness=100, damping=10)
    with pytest.raises(PermissionError):
        other.rope(body, (200, 20), (0, 0), max_length=120)
    with pytest.raises(PermissionError):
        other.sensor_polygon(body, ((-10, -10), (10, -10), (0, 10)))
