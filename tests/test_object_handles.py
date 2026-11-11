import pytest

from ebm.tile_api import (
    BALL_COLLISION_TYPE,
    BALL_ELASTICITY,
    BALL_FRICTION,
    DEFAULT_BALL_FILL,
    DEFAULT_BALL_STROKE,
    TileBuilder,
    TileResourceRegistry,
    ball_shape_filter,
)


def setup_world(origin=(0, 0)):
    import pymunk

    space = pymunk.Space()
    registry = TileResourceRegistry.for_space(space)
    builder = TileBuilder(registry, 1, origin)
    return pymunk, space, registry, builder


def add_ball(pymunk, space, position=(100, 100)):
    body = pymunk.Body(1, pymunk.moment_for_circle(1, 0, 8))
    body.position = position
    shape = pymunk.Circle(body, 8)
    shape.friction = BALL_FRICTION
    shape.elasticity = BALL_ELASTICITY
    shape.ebm_fill_color = DEFAULT_BALL_FILL
    shape.ebm_stroke_color = DEFAULT_BALL_STROKE
    shape.collision_type = BALL_COLLISION_TYPE
    shape.filter = ball_shape_filter()
    space.add(body, shape)
    return body, shape


def contact_ball(registry, owner, body, shape):
    return registry._claim_ball(owner, body, shape)


def test_visual_segment_endpoints_can_be_moved():
    _, _, registry, builder = setup_world()
    visual = builder.visual_segment((20, 40), (180, 40))
    visual.set_segment_points((30, 50), (160, 170))
    raw = registry.resolve(1, visual)
    assert raw.a == (30.0, 50.0)
    assert raw.b == (160.0, 170.0)


def test_shape_and_visual_handles_share_pause_resume():
    _, space, registry, builder = setup_world()
    shape = builder.static_segment((20, 20), (180, 20), 2)
    visual = builder.visual_segment((20, 40), (180, 40))
    raw_shape = registry.resolve(1, shape)

    shape.pause()
    visual.pause()
    assert raw_shape not in space.shapes
    assert builder.visual_items == []

    shape.resume()
    visual.resume(delay=.2)
    assert raw_shape in space.shapes
    assert len(builder.visual_items) == 1
    registry.advance(.1)
    assert len(builder.visual_items) == 1
    registry.advance(.1)
    assert len(builder.visual_items) == 2


def test_shape_material_setters_validate_values():
    _, _, registry, builder = setup_world()
    shape = builder.static_circle((100, 100), 20)
    raw = registry.resolve(1, shape)
    shape.set_friction(1.2)
    shape.set_elasticity(.9)
    assert raw.friction == pytest.approx(1.2)
    assert raw.elasticity == pytest.approx(.9)
    with pytest.raises(ValueError): shape.set_friction(-1)
    with pytest.raises(ValueError): shape.set_elasticity(1.1)


def test_ball_uses_shared_api_and_restores_at_handoff():
    pymunk, space, registry, _ = setup_world()
    body, shape = add_ball(pymunk, space)
    ball = contact_ball(registry, 1, body, shape)

    ball.set_fill_color((255, 0, 0, 255))
    ball.set_stroke_color((255, 255, 255, 255))
    ball.set_friction(.9)
    ball.set_elasticity(.1)
    ball.set_position((120, 80))
    ball.set_velocity((10, 20))
    assert ball.position == pytest.approx((120, 80))
    assert ball.velocity == pytest.approx((10, 20))

    body.position = (420, 80)
    registry.advance(0)
    assert shape.friction == pytest.approx(BALL_FRICTION)
    assert shape.elasticity == pytest.approx(BALL_ELASTICITY)
    assert shape.ebm_fill_color == DEFAULT_BALL_FILL
    assert shape.ebm_stroke_color == DEFAULT_BALL_STROKE
    with pytest.raises(PermissionError): ball.set_velocity((0, 0))


def test_ball_pause_resume_preserves_identity_and_delay():
    pymunk, space, registry, _ = setup_world()
    body, shape = add_ball(pymunk, space)
    ball = contact_ball(registry, 1, body, shape)

    ball.pause()
    assert ball.paused
    assert body not in space.bodies and shape not in space.shapes
    ball.resume(delay=.2)
    registry.advance(.1)
    assert ball.paused
    registry.advance(.1)
    assert not ball.paused
    assert body in space.bodies and shape in space.shapes


def test_ball_position_must_keep_complete_ball_inside_tile():
    pymunk, space, registry, _ = setup_world()
    body, shape = add_ball(pymunk, space)
    ball = contact_ball(registry, 1, body, shape)
    with pytest.raises(ValueError): ball.set_position((4, 100))


def test_boundary_ball_can_be_paused_but_must_move_inside_before_resume():
    pymunk, space, registry, _ = setup_world()
    body, shape = add_ball(pymunk, space, position=(4, 100))
    ball = contact_ball(registry, 1, body, shape)

    ball.pause()
    assert ball.paused
    with pytest.raises(ValueError, match="complete ball"):
        ball.resume()

    ball.set_position((100, 300))
    ball.set_velocity((0, 200))
    ball.resume()
    assert not ball.paused
    assert ball.position == pytest.approx((100, 300))


def test_ball_wholly_outside_tile_cannot_be_paused():
    pymunk, space, registry, _ = setup_world()
    body, shape = add_ball(pymunk, space, position=(-9, 100))
    ball = contact_ball(registry, 1, body, shape)
    with pytest.raises(ValueError, match="overlap the tile"):
        ball.pause()


def test_ball_center_force_impulse_and_torque():
    pymunk, space, registry, _ = setup_world()
    body, shape = add_ball(pymunk, space)
    ball = contact_ball(registry, 1, body, shape)

    ball.apply_impulse((2, 3))
    assert ball.velocity == pytest.approx((2, 3))
    assert body.angular_velocity == 0
    ball.apply_force((4, 6))
    assert body.force == pytest.approx((4, 6))
    assert body.torque == 0
    ball.apply_torque(8)
    ball.apply_torque(-2)
    assert body.torque == 6
    space.step(.25)
    assert ball.velocity == pytest.approx((3, 4.5))
    assert body.angular_velocity == pytest.approx(6 / body.moment * .25)


@pytest.mark.parametrize("method, accumulator", [
    ("apply_force", "torque"), ("apply_impulse", "angular_velocity"),
])
def test_ball_off_center_actions_match_body_local_coordinates(method, accumulator):
    import math

    pymunk, space, registry, _ = setup_world(origin=(400, 0))
    body, shape = add_ball(pymunk, space, position=(500, 100))
    body.angle = math.pi / 2
    ball = contact_ball(registry, 1, body, shape)
    getattr(ball, method)((0, 4), (2, 0))
    if method == "apply_force":
        assert body.force == pytest.approx((-4, 0))
        assert getattr(body, accumulator) == pytest.approx(8)
    else:
        assert ball.velocity == pytest.approx((-4, 0))
        assert getattr(body, accumulator) == pytest.approx(8 / body.moment)


@pytest.mark.parametrize("method, args", [
    ("apply_force", ((1, 2),)),
    ("apply_impulse", ((1, 2),)),
    ("apply_torque", (3,)),
])
def test_ball_actions_reject_stale_handles_after_handoff_and_reclaim(method, args):
    pymunk, space, registry, _ = setup_world()
    body, shape = add_ball(pymunk, space)
    old = contact_ball(registry, 1, body, shape)
    body.position = (420, 100)
    registry.advance(0)
    with pytest.raises(PermissionError):
        getattr(old, method)(*args)
    body.position = (100, 100)
    current = contact_ball(registry, 1, body, shape)
    with pytest.raises(PermissionError):
        getattr(old, method)(*args)
    assert body.force == (0, 0)
    assert body.velocity == (0, 0)
    assert body.torque == 0
    getattr(current, method)(*args)


@pytest.mark.parametrize("torque", [float("nan"), float("inf"), -float("inf"), "invalid"])
def test_ball_torque_validation_leaves_existing_torque_unchanged(torque):
    pymunk, space, registry, _ = setup_world()
    body, shape = add_ball(pymunk, space)
    ball = contact_ball(registry, 1, body, shape)
    ball.apply_torque(5)
    with pytest.raises((ValueError, TypeError)):
        ball.apply_torque(torque)
    assert body.torque == 5
