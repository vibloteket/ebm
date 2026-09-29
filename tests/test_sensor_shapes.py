import pymunk
import pytest

from ebm.geometry_bounds import GeometryBoundsError
from ebm.tile_api import BALL_COLLISION_TYPE, TileBuilder, TileResourceRegistry


def world():
    space = pymunk.Space()
    registry = TileResourceRegistry.for_space(space)
    return space, registry, TileBuilder(registry, 1, (0, 0))


def make_ball(space, position, velocity):
    body = pymunk.Body(1, 1)
    body.position = position
    body.velocity = velocity
    shape = pymunk.Circle(body, 15)
    shape.collision_type = BALL_COLLISION_TYPE
    space.add(body, shape)
    return body


def test_static_sensor_circle_detects_without_colliding():
    space, registry, b = world()
    sensor = b.sensor_circle((200, 200), 60)
    raw = registry.resolve(1, sensor)
    assert raw.sensor and raw.ebm_hidden
    assert raw.body is space.static_body
    contacts = []
    b.on_ball_contact(sensor, begin=lambda event: contacts.append(event.ball))
    ball = make_ball(space, (80, 200), (120, 0))
    for _ in range(72):
        space.step(1 / 120)
    assert ball.position == pytest.approx((152, 200))
    assert ball.velocity == pytest.approx((120, 0))
    assert contacts


def test_static_sensor_segment_detects_crossing():
    space, registry, b = world()
    sensor = b.sensor_segment((100, 200), (300, 200), radius=4)
    assert registry.resolve(1, sensor).sensor
    contacts = []
    b.on_ball_contact(sensor, begin=lambda event: contacts.append(event.ball))
    ball = make_ball(space, (200, 100), (0, 240))
    for _ in range(60):
        space.step(1 / 120)
    assert ball.velocity == pytest.approx((0, 240))
    assert contacts


def test_static_sensor_polygon_and_box_need_no_body():
    space, registry, b = world()
    polygon = b.sensor_polygon(((100, 100), (300, 100), (300, 300)))
    box = b.sensor_box(40, 40, 360, 360)
    for handle in (polygon, box):
        raw = registry.resolve(1, handle)
        assert raw.sensor and raw.body is space.static_body


def test_body_attached_sensors_are_massless_and_follow_body_pause_resume():
    space, registry, b = world()
    body = b.dynamic_body((200, 200))
    b.circle_shape(body, (0, 0), 10, density=.01)
    raw_body = registry.resolve(1, body)
    mass, moment = raw_body.mass, raw_body.moment
    sensors = [
        b.sensor_segment((-60, 0), (60, 0), 2, body=body),
        b.sensor_circle((0, 30), 12, body=body),
        b.sensor_polygon(((-20, -20), (20, -20), (0, 20)), body=body),
        b.sensor_box(-60, -10, 60, 10, body=body),
    ]
    assert (raw_body.mass, raw_body.moment) == pytest.approx((mass, moment))
    for sensor in sensors:
        assert registry.resolve(1, sensor).sensor
    body.pause()
    assert not space.shapes and not space.bodies
    body.resume()
    assert len(space.shapes) == 5 and len(space.bodies) == 1
    registry.destroy_owner(1)
    assert not space.shapes and not space.bodies


def test_body_attached_sensor_uses_body_local_coordinates():
    space, registry, b = world()
    body = b.dynamic_body((200, 100))
    b.circle_shape(body, (0, 0), 10, density=.01)
    contacts = []
    b.on_ball_contact(b.sensor_circle((0, 0), 40, body=body), begin=lambda event: contacts.append(event.ball))
    ball = make_ball(space, (120, 100), (60, 0))
    for _ in range(60):
        space.step(1 / 120)
    assert contacts
    assert ball.velocity == pytest.approx((60, 0))


@pytest.mark.parametrize("construct,edge,overflow", [
    (lambda b: b.sensor_circle((5, 20), 10), "left", 5),
    (lambda b: b.sensor_segment((0, 100), (0, 300), 10), "left", 10),
    (lambda b: b.sensor_polygon(((2, 100), (30, 100), (30, 150)), radius=3), "left", 1),
    (lambda b: b.sensor_box(-1, 10, 30, 40), "left", 1),
    (lambda b: b.static_box(100, 396, 200, 404), "bottom", 4),
])
def test_sensor_and_box_overhang_is_rejected_before_registering(construct, edge, overflow):
    space, registry, b = world()
    with pytest.raises(GeometryBoundsError) as caught:
        construct(b)
    assert caught.value.details["edge"] == edge
    assert caught.value.details["overflow"] == pytest.approx(overflow)
    assert not space.shapes and not registry.owned_objects(1)


def test_body_attached_sensor_rejects_world_overhang_at_authored_pose():
    space, registry, b = world()
    body = b.dynamic_body((10, 200))
    before = len(registry.owned_objects(1))
    with pytest.raises(GeometryBoundsError):
        b.sensor_circle((0, 0), 20, body=body)
    assert len(registry.owned_objects(1)) == before
    assert not space.shapes


def test_sensor_radius_limits_match_shape_families():
    _, _, b = world()
    with pytest.raises(ValueError):
        b.sensor_segment((100, 100), (200, 100), 21)
    with pytest.raises(ValueError):
        b.sensor_polygon(((100, 100), (200, 100), (200, 200)), radius=21)
    with pytest.raises(ValueError):
        b.sensor_circle((100, 100), -1)
    b.sensor_segment((100, 100), (200, 100), 20)
    b.sensor_polygon(((100, 100), (200, 100), (200, 200)), radius=20)


def test_cross_owner_sensor_body_is_rejected():
    space, registry, b = world()
    body = b.dynamic_body((200, 200))
    other = TileBuilder(registry, 2, (400, 0))
    for construct in (
        lambda: other.sensor_circle((0, 0), 10, body=body),
        lambda: other.sensor_segment((-10, 0), (10, 0), 2, body=body),
        lambda: other.sensor_box(-10, -10, 10, 10, body=body),
    ):
        with pytest.raises(PermissionError):
            construct()


def test_static_box_is_solid_and_styled():
    space, registry, b = world()
    space.gravity = (0, 1800)
    box = b.static_box(40, 300, 360, 320, fill_color=(1, 2, 3, 255))
    raw = registry.resolve(1, box)
    assert not raw.sensor and raw.body is space.static_body
    ball = make_ball(space, (200, 100), (0, 0))
    for _ in range(480):
        space.step(1 / 120)
    assert ball.position == pytest.approx((200, 285), abs=2)


def test_box_shape_adds_mass_and_is_bounds_checked_at_authored_pose():
    space, registry, b = world()
    body = b.dynamic_body((200, 200))
    b.circle_shape(body, (0, 0), 10, density=.01)
    raw_body = registry.resolve(1, body)
    mass = raw_body.mass
    b.box_shape(body, -40, -10, 40, 10)
    assert raw_body.mass > mass
    edge_body = b.dynamic_body((10, 200))
    before = len(registry.owned_objects(1))
    with pytest.raises(GeometryBoundsError):
        b.box_shape(edge_body, -40, -10, 40, 10)
    assert len(registry.owned_objects(1)) == before
