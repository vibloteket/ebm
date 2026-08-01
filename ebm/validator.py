from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .ports import INPUT_PORTS, OUTPUT_PORTS, PORT_SPECS, Port
from .tile_api import (
    BALL_COLLISION_TYPE,
    BALL_ELASTICITY,
    BALL_FRICTION,
    TileBuilder,
    TileResourceRegistry,
    ball_shape_filter,
)

BALL_RADIUS = 8
BALL_MASS = 1
DEFAULT_DT = 1 / 240
DEFAULT_DURATION = 12.0
EXIT_TOLERANCE = 28
EXIT_SPEED = 20
BOUNDS_EPSILON = 0.25
STUCK_SPEED = 6
STUCK_AFTER = 3.0


@dataclass
class ValidationBall:
    entry: Port
    body: Any
    shape: Any
    slow_since: float | None = None


@dataclass
class ValidationResult:
    name: str
    duration: float
    balls_spawned: int = 0
    exited: int = 0
    unexpected: int = 0
    out_of_bounds: int = 0
    stuck: int = 0
    active: int = 0
    output_counts: dict[str, int] = field(default_factory=lambda: {port.name: 0 for port in OUTPUT_PORTS})
    details: list[dict[str, Any]] = field(default_factory=list)

    @property
    def all_outputs_used(self) -> bool:
        return all(self.output_counts.values())

    @property
    def ok(self) -> bool:
        return (
            self.unexpected == 0
            and self.out_of_bounds == 0
            and self.stuck == 0
            and self.active == 0
            and self.exited == self.balls_spawned
            and self.all_outputs_used
        )

    @property
    def pass_ratio(self) -> float:
        return self.exited / self.balls_spawned if self.balls_spawned else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "duration": self.duration,
            "balls_spawned": self.balls_spawned,
            "exited": self.exited,
            "unexpected": self.unexpected,
            "out_of_bounds": self.out_of_bounds,
            "stuck": self.stuck,
            "active": self.active,
            "output_counts": self.output_counts,
            "all_outputs_used": self.all_outputs_used,
            "pass_ratio": self.pass_ratio,
            "ok": self.ok,
            "details": self.details,
        }


def validate_tile_port_spec(
    tile_factory: Callable[[], Any],
    *,
    name: str = "tile flow",
    duration: float = DEFAULT_DURATION,
    dt: float = DEFAULT_DT,
) -> ValidationResult:
    """Validate every input state; any valid output is accepted, and all outputs must be used."""
    import pymunk

    space = pymunk.Space()
    space.gravity = (0, 900)
    tile = tile_factory()
    registry = TileResourceRegistry.for_space(space)
    builder = TileBuilder(registry, 1, (0, 0))
    tile.build(builder)
    result = ValidationResult(name=name, duration=duration)

    for entry in (Port.T0, Port.L0, Port.R0):
        spec = PORT_SPECS[entry]
        _, combinations = spec.sample_values()
        for dx, dy, dvx, dvy in combinations:
            ball = _spawn_ball(space, entry, dx, dy, dvx, dvy)
            result.balls_spawned += 1
            outcome = _run_one(space, tile, builder, ball, duration, dt)
            result.details.append(outcome)
            status = outcome["status"]
            if status == "exited":
                result.exited += 1
                result.output_counts[outcome["exit"]] += 1
            elif status == "unexpected":
                result.unexpected += 1
            elif status == "out_of_bounds":
                result.out_of_bounds += 1
            elif status == "stuck":
                result.stuck += 1
            else:
                result.active += 1
            _remove_ball(space, ball)

    registry.destroy_owner(1)
    return result


def _run_one(space, tile, builder, ball: ValidationBall, duration: float, dt: float) -> dict[str, Any]:
    t = 0.0
    for _ in range(int(duration / dt)):
        tile.update(builder, dt)
        space.step(dt)
        t += dt
        classification = _classify_ball(ball.body.position, ball.body.velocity)
        if classification is not None:
            status, label = classification
            return _detail(ball, status, label, t)
        if ball.body.velocity.length < STUCK_SPEED:
            if ball.slow_since is None:
                ball.slow_since = t
            elif t - ball.slow_since >= STUCK_AFTER:
                return _detail(ball, "stuck", "settled", t)
        else:
            ball.slow_since = None
    return _detail(ball, "active", None, duration)


def _spawn_ball(space, entry: Port, dx: float, dy: float, dvx: float, dvy: float) -> ValidationBall:
    import pymunk

    spec = PORT_SPECS[entry]
    base_vx, base_vy = _entry_base_velocity(entry)
    if entry == Port.T0:
        position = (spec.x_center + dx, spec.y_center + BALL_RADIUS + dy)
    elif entry == Port.L0:
        position = (spec.x_center + BALL_RADIUS + dx, spec.y_center + dy)
    else:
        position = (spec.x_center - BALL_RADIUS + dx, spec.y_center + dy)
    x = max(BALL_RADIUS + .5, min(200 - BALL_RADIUS - .5, position[0]))
    y = max(BALL_RADIUS + .5, min(200 - BALL_RADIUS - .5, position[1]))
    body = pymunk.Body(BALL_MASS, pymunk.moment_for_circle(BALL_MASS, 0, BALL_RADIUS))
    body.position = (x, y)
    body.velocity = (base_vx + dvx, base_vy + dvy)
    shape = pymunk.Circle(body, BALL_RADIUS)
    shape.friction = BALL_FRICTION
    shape.elasticity = BALL_ELASTICITY
    shape.collision_type = BALL_COLLISION_TYPE
    shape.filter = ball_shape_filter()
    space.add(body, shape)
    return ValidationBall(entry, body, shape)


def _entry_base_velocity(entry: Port) -> tuple[float, float]:
    if entry == Port.T0:
        return 0, 70
    if entry == Port.L0:
        return 110, 0
    return -110, 0


def _classify_ball(position, velocity) -> tuple[str, str | None] | None:
    x, y = float(position.x), float(position.y)
    vx, vy = float(velocity.x), float(velocity.y)
    for port in (Port.B0, Port.L1, Port.R1):
        if _in_exit_aperture(port, x, y, vx, vy):
            spec = PORT_SPECS[port]
            if _satisfies_exit_spec(port, spec, x, y, vx, vy):
                return "exited", port.name
            return "unexpected", f"bad-exit-spec:{port.name}"
    if not _ball_fully_inside_tile(x, y):
        return "out_of_bounds", _bounds_label(x, y)
    return None


def _in_exit_aperture(port: Port, x: float, y: float, vx: float, vy: float) -> bool:
    if not _ball_fully_inside_tile(x, y):
        return False
    if port == Port.B0:
        return abs(x - 100) <= EXIT_TOLERANCE and y >= 200 - BALL_RADIUS - 2 and vy >= EXIT_SPEED
    if port == Port.L1:
        return x <= BALL_RADIUS + 2 and abs(y - 150) <= EXIT_TOLERANCE and vx <= -EXIT_SPEED
    return x >= 200 - BALL_RADIUS - 2 and abs(y - 50) <= EXIT_TOLERANCE and vx >= EXIT_SPEED


def _satisfies_exit_spec(port, spec, x, y, vx, vy) -> bool:
    if abs(x - spec.x_center) > spec.x_range + EXIT_TOLERANCE or abs(y - spec.y_center) > spec.y_range + EXIT_TOLERANCE:
        return False
    if port == Port.B0:
        return vy >= spec.vy_min
    if port == Port.L1:
        return vx <= -spec.vx_min and abs(vy) <= spec.exit_vy_range
    return vx >= spec.vx_min and abs(vy) <= spec.exit_vy_range


def _ball_fully_inside_tile(x: float, y: float) -> bool:
    return BALL_RADIUS - BOUNDS_EPSILON <= x <= 200 - BALL_RADIUS + BOUNDS_EPSILON and BALL_RADIUS - BOUNDS_EPSILON <= y <= 200 - BALL_RADIUS + BOUNDS_EPSILON


def _bounds_label(x: float, y: float) -> str:
    if y < BALL_RADIUS - BOUNDS_EPSILON: return "top"
    if y > 200 - BALL_RADIUS + BOUNDS_EPSILON: return "bottom"
    if x < BALL_RADIUS - BOUNDS_EPSILON: return "left"
    if x > 200 - BALL_RADIUS + BOUNDS_EPSILON: return "right"
    return "bounds"


def _detail(ball, status, label, t):
    return {
        "entry": ball.entry.name,
        "status": status,
        "exit": label,
        "finished_at": round(t, 3),
        "finish_pos": [round(float(ball.body.position.x), 2), round(float(ball.body.position.y), 2)],
        "finish_vel": [round(float(ball.body.velocity.x), 2), round(float(ball.body.velocity.y), 2)],
    }


def _remove_ball(space, ball):
    try:
        space.remove(ball.shape, ball.body)
    except Exception:
        pass
