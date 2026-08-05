from ebm.validator import ValidationBall, _classify_ball


def _ball(x, y, vx=0, vy=0, radius=8):
    import pymunk

    space = pymunk.Space()
    body = pymunk.Body(1, 1)
    body.position = x, y
    body.velocity = vx, vy
    shape = pymunk.Circle(body, radius)
    space.add(body, shape)
    return space, ValidationBall(1, None, body, shape, 0)


def test_partial_top_exit_is_allowed_until_whole_ball_crosses():
    space, ball = _ball(100, -4, vy=-100, radius=8)
    assert _classify_ball(space, ball) is None
    ball.body.position = 100, -8.5
    assert _classify_ball(space, ball) == ("invalid", "top")


def test_side_exit_waits_until_whole_ball_crosses():
    space, ball = _ball(-4, 150, vx=-100, radius=8)
    assert _classify_ball(space, ball) is None
    ball.body.position = -8.5, 150
    assert _classify_ball(space, ball) == ("exited", "L1")


def test_b0_checks_angle_instead_of_fixed_transverse_speed():
    # High transverse speed is fine when the complete vector is within 30°.
    space, ball = _ball(100, 208.5, vx=140, vy=260, radius=8)
    assert _classify_ball(space, ball) == ("exited", "B0")
    ball.body.velocity = 160, 240
    assert _classify_ball(space, ball) == ("invalid", "bad-exit-angle:B0")


def test_side_exit_requires_outward_direction_within_30_degrees():
    space, ball = _ball(-8.5, 150, vx=-260, vy=140, radius=8)
    assert _classify_ball(space, ball) == ("exited", "L1")
    ball.body.velocity = -240, 160
    assert _classify_ball(space, ball) == ("invalid", "bad-exit-angle:L1")
    ball.body.velocity = 100, 0
    assert _classify_ball(space, ball) == ("invalid", "bad-exit-angle:L1")


def test_slow_outward_exit_has_no_minimum_speed():
    space, ball = _ball(100, 208.5, vx=0, vy=.1, radius=8)
    assert _classify_ball(space, ball) == ("exited", "B0")


def test_exit_boundary_uses_actual_ball_radius():
    space, ball = _ball(100, 211, vx=0, vy=1, radius=12)
    assert _classify_ball(space, ball) is None
    ball.body.position = 100, 212.5
    assert _classify_ball(space, ball) == ("exited", "B0")
