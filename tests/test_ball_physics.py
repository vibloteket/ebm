import pytest

from ebm.ball_physics import MAX_BALL_SPEED, configure_ball_body, limit_ball_speed


def test_speed_limiter_scales_vector_and_preserves_direction():
    import pymunk

    body = pymunk.Body(1, 1)
    body.velocity = 600, 800
    limit_ball_speed(body)
    assert body.velocity.length == pytest.approx(MAX_BALL_SPEED)
    assert body.velocity.x == pytest.approx(360)
    assert body.velocity.y == pytest.approx(480)


def test_velocity_callback_caps_after_gravity_integration():
    import pymunk

    body = pymunk.Body(1, 1)
    configure_ball_body(body)
    body.velocity = 0, 598
    body.velocity_func(body, (0, 1800), 1, 1 / 60)
    assert body.velocity.length == pytest.approx(MAX_BALL_SPEED)


def test_speed_below_limit_is_unchanged():
    import pymunk

    body = pymunk.Body(1, 1)
    body.velocity = 240, -160
    limit_ball_speed(body)
    assert tuple(body.velocity) == pytest.approx((240, -160))
