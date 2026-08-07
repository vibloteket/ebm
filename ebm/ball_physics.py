from __future__ import annotations

import math

MAX_BALL_SPEED = 600.0


def limit_ball_speed(body, _gravity=None, _damping=None, _dt=None) -> None:
    """Clamp a body's velocity vector without changing its direction."""
    vx, vy = float(body.velocity.x), float(body.velocity.y)
    speed_squared = vx * vx + vy * vy
    if not math.isfinite(speed_squared) or speed_squared <= MAX_BALL_SPEED * MAX_BALL_SPEED:
        return
    scale = MAX_BALL_SPEED / math.sqrt(speed_squared)
    body.velocity = vx * scale, vy * scale


def ball_velocity_func(body, gravity, damping, dt) -> None:
    """Pymunk velocity callback that integrates normally, then applies the cap."""
    import pymunk

    pymunk.Body.update_velocity(body, gravity, damping, dt)
    limit_ball_speed(body)


def configure_ball_body(body) -> None:
    body.velocity_func = ball_velocity_func


def limit_space_ball_speeds(balls) -> None:
    """Re-apply after collision callbacks that may directly change velocity."""
    for ball in balls:
        limit_ball_speed(ball.body)
