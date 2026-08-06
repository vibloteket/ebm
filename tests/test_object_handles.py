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

    body.position = (220, 80)
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
