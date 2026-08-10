import pytest

from ebm.tile_api import (
    BALL_COLLISION_TYPE,
    BALL_ELASTICITY,
    BALL_FRICTION,
    TileBuilder,
    TileResourceRegistry,
    ball_shape_filter,
)


def world(*, sensor: bool):
    import pymunk

    space = pymunk.Space()
    registry = TileResourceRegistry.for_space(space)
    builder = TileBuilder(registry, 1, (0, 0))
    shape = builder.sensor_box(90, 90, 110, 110) if sensor else builder.static_circle((100, 100), 20)
    body = pymunk.Body(1, pymunk.moment_for_circle(1, 0, 8))
    body.position = (60, 100)
    body.velocity = (100, 0)
    ball = pymunk.Circle(body, 8)
    ball.friction = BALL_FRICTION
    ball.elasticity = BALL_ELASTICITY
    ball.collision_type = BALL_COLLISION_TYPE
    ball.filter = ball_shape_filter()
    space.add(body, ball)
    return space, builder, shape, body


def step(space, count=480):
    for _ in range(count):
        space.step(1 / 240)


def test_contact_phases_and_event_data_for_physical_shape():
    space, builder, shape, body = world(sensor=False)
    phases = []
    events = {}

    def record(name):
        def callback(event):
            phases.append(name)
            events[name] = event
        return callback

    builder.on_ball_contact(
        shape,
        begin=record("begin"),
        pre_solve=record("pre_solve"),
        post_solve=record("post_solve"),
        separate=record("separate"),
    )
    step(space)

    assert phases.count("begin") == 1
    assert phases.count("separate") == 1
    assert phases.count("pre_solve") >= 1
    assert phases.count("post_solve") >= 1
    assert events["begin"].point is not None
    assert events["begin"].normal is not None
    assert events["post_solve"].impulse is not None
    assert events["post_solve"].kinetic_energy is not None
    assert events["begin"].impulse is None
    assert body.velocity.x < 0  # The physical circle still collides.


def test_sensor_remains_non_colliding_and_supports_begin_separate():
    space, builder, shape, body = world(sensor=True)
    phases = []
    builder.on_ball_contact(
        shape,
        begin=lambda event: phases.append("begin"),
        separate=lambda event: phases.append("separate"),
    )
    step(space)
    assert phases == ["begin", "separate"]
    assert body.velocity.x == pytest.approx(100)


def test_begin_can_disable_physical_collision():
    space, builder, shape, body = world(sensor=False)
    builder.on_ball_contact(shape, begin=lambda event: False)
    step(space)
    assert body.velocity.x == pytest.approx(100)


def test_contact_registration_requires_a_phase():
    _, builder, shape, _ = world(sensor=True)
    with pytest.raises(ValueError, match="at least one"):
        builder.on_ball_contact(shape)
