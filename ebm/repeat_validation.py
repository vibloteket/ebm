from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
import traceback
from typing import Any, Callable

from .ball_physics import configure_ball_body, limit_ball_speed
from .ports import BALL_RADIUS, COLUMN_OFFSET, MAX_EXIT_ANGLE_DEGREES, PORT_SPECS, TILE_SIZE, Port, entry_velocity, tile_origin
from .tile_api import BALL_COLLISION_TYPE, BALL_ELASTICITY, BALL_FRICTION, TileBuilder, TileResourceRegistry, ball_shape_filter


@dataclass
class RepeatValidationResult:
    name: str = "3 × 3 repeat"
    balls_spawned: int = 0
    exited: int = 0
    active: int = 0
    peak_active: int = 0
    lost: int = 0
    capacity_exceeded: bool = False
    runtime_errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (
            self.balls_spawned > 0
            and self.exited > 0
            and self.lost == 0
            and not self.capacity_exceeded
            and not self.runtime_errors
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "balls_spawned": self.balls_spawned,
            "exited": self.exited,
            "active": self.active,
            "peak_active": self.peak_active,
            "lost": self.lost,
            "capacity_exceeded": self.capacity_exceeded,
            "runtime_errors": self.runtime_errors,
            "ok": self.ok,
        }


def validate_repeated_flow(
    tile_factory: Callable[[], Any],
    *,
    size: int = 3,
    duration: float = 30.0,
    spawn_interval: float = 0.8,
    max_active_per_tile: int = 20,
    dt: float = 1 / 120,
    seed: int = 17,
) -> RepeatValidationResult:
    """Run a deterministic repeated-grid integration test with real handoffs."""
    import pymunk

    result = RepeatValidationResult()
    space = pymunk.Space()
    space.gravity = (0, 1800)
    registry = TileResourceRegistry.for_space(space)
    owners = []
    owner = 1
    for row in range(size):
        for col in range(size):
            tile = tile_factory()
            builder = TileBuilder(registry, owner, tile_origin(row, col))
            try:
                tile.build(builder)
            except Exception as error:
                result.runtime_errors.append(_error(error, owner, "build", size))
                return result
            owners.append((owner, tile, builder))
            owner += 1

    boundaries = [(Port.T0, *tile_origin(0, col)) for col in range(size)]
    boundaries += [(Port.L0, *tile_origin(row, 0)) for row in range(size)]
    rng = random.Random(seed)
    clocks = {boundary: rng.uniform(0.05, spawn_interval) for boundary in boundaries}
    balls = []
    t = 0.0
    max_active = size * size * max_active_per_tile
    edge_x = size * TILE_SIZE
    edge_y = size * TILE_SIZE + COLUMN_OFFSET

    while t < duration and not result.runtime_errors:
        for boundary in boundaries:
            clocks[boundary] -= dt
            if clocks[boundary] <= 0:
                balls.append(_spawn(space, boundary, rng))
                result.balls_spawned += 1
                clocks[boundary] += spawn_interval
        for owner, tile, builder in owners:
            try:
                tile.update(builder, dt)
            except Exception as error:
                result.runtime_errors.append(_error(error, owner, "update", size))
                break
        if result.runtime_errors:
            break
        space.step(dt)
        registry.advance(dt)
        if registry.runtime_errors:
            result.runtime_errors.extend(_located(error, size) for error in registry.runtime_errors)
            break
        for body, _shape in balls:
            limit_ball_speed(body)
        for ball in list(balls):
            body, shape = ball
            x, y = body.position
            if not all(math.isfinite(float(value)) for value in (x, y, body.velocity.x, body.velocity.y)):
                result.lost += 1
                _remove(space, balls, ball)
            elif x < -200 or x > edge_x + 200 or y < -200 or y > edge_y + 300:
                result.exited += 1
                _remove(space, balls, ball)
        result.active = len(balls)
        result.peak_active = max(result.peak_active, result.active)
        if result.active > max_active:
            result.capacity_exceeded = True
            break
        t += dt

    result.active = len(balls)
    for ball in list(balls):
        _remove(space, balls, ball)
    for owner, _, _ in owners:
        registry.destroy_owner(owner)
    return result


def _spawn(space, boundary, rng):
    import pymunk
    port, ox, oy = boundary
    spec = PORT_SPECS[port]
    offset = rng.uniform(-spec.x_range, spec.x_range) if port == Port.T0 else rng.uniform(-spec.y_range, spec.y_range)
    speed = rng.uniform(1, 600)
    vx, vy = entry_velocity(port, speed, rng.uniform(-MAX_EXIT_ANGLE_DEGREES, MAX_EXIT_ANGLE_DEGREES))
    position = (ox + spec.x_center + offset, oy + BALL_RADIUS + .5) if port == Port.T0 else (ox + BALL_RADIUS + .5, oy + spec.y_center + offset)
    body = pymunk.Body(1, pymunk.moment_for_circle(1, 0, BALL_RADIUS))
    configure_ball_body(body)
    body.position = position
    body.velocity = vx, vy
    shape = pymunk.Circle(body, BALL_RADIUS)
    shape.friction = BALL_FRICTION
    shape.elasticity = BALL_ELASTICITY
    shape.collision_type = BALL_COLLISION_TYPE
    shape.filter = ball_shape_filter()
    space.add(body, shape)
    return body, shape


def _located(error, size):
    item = dict(error)
    owner = int(item.get("owner", 0))
    if owner:
        row, col = divmod(owner - 1, size)
        item.update({"row": row, "col": col})
    return item


def _error(error, owner, phase, size):
    return _located({"owner": owner, "phase": phase, "type": type(error).__name__, "message": str(error), "traceback": "".join(traceback.format_exception(error))}, size)


def _remove(space, balls, ball):
    body, shape = ball
    try:
        space.remove(shape, body)
    except Exception:
        pass
    balls.remove(ball)
