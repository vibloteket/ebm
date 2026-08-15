from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
import traceback
from typing import Any, Callable

from .ball_physics import configure_ball_body, limit_space_ball_speeds
from .ports import BALL_RADIUS, COLUMN_OFFSET, MAX_EXIT_ANGLE_DEGREES, OUTPUT_PORTS, PORT_SPECS, TILE_SIZE, Port, entry_flow_samples, entry_velocity, tile_origin
from .tile_api import (
    BALL_COLLISION_TYPE,
    BALL_ELASTICITY,
    BALL_FRICTION,
    TileBuilder,
    TileResourceRegistry,
    ball_shape_filter,
)

BALL_MASS = 1
DEFAULT_DT = 1 / 120
VALIDATION_BALLS = 120
MAX_ACTIVE_BALLS = 20
SPAWN_INTERVAL = 0.4
BOUNDS_EPSILON = 0.25
MAX_EXIT_ANGLE_COSINE = math.cos(math.radians(MAX_EXIT_ANGLE_DEGREES))


@dataclass
class ValidationBall:
    id: int
    entry: Port
    body: Any
    shape: Any
    spawned_at: float
    trajectory: list[list[float]] = field(default_factory=list)
    next_sample_at: float = 0.0


@dataclass
class ValidationResult:
    name: str
    balls_target: int
    max_active_allowed: int
    balls_spawned: int = 0
    exited: int = 0
    active: int = 0
    peak_active: int = 0
    invalid: int = 0
    lost: int = 0
    capacity_exceeded: bool = False
    output_counts: dict[str, int] = field(default_factory=lambda: {port.name: 0 for port in OUTPUT_PORTS})
    details: list[dict[str, Any]] = field(default_factory=list)
    runtime_errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def all_outputs_used(self) -> bool:
        return all(self.output_counts.values())

    @property
    def conserved(self) -> bool:
        return self.exited + self.active + self.invalid + self.lost == self.balls_spawned

    @property
    def ok(self) -> bool:
        return (
            self.balls_spawned == self.balls_target
            and self.invalid == 0
            and self.lost == 0
            and self.conserved
            and not self.capacity_exceeded
            and self.active <= self.max_active_allowed
            and self.all_outputs_used
            and not self.runtime_errors
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "balls_target": self.balls_target,
            "max_active_allowed": self.max_active_allowed,
            "balls_spawned": self.balls_spawned,
            "exited": self.exited,
            "active": self.active,
            "peak_active": self.peak_active,
            "invalid": self.invalid,
            "lost": self.lost,
            "capacity_exceeded": self.capacity_exceeded,
            "output_counts": self.output_counts,
            "all_outputs_used": self.all_outputs_used,
            "conserved": self.conserved,
            "ok": self.ok,
            "details": self.details,
            "runtime_errors": self.runtime_errors,
        }


def validate_tile_flow(
    tile_factory: Callable[[], Any],
    *,
    name: str = "tile flow",
    balls: int = VALIDATION_BALLS,
    max_active: int = MAX_ACTIVE_BALLS,
    spawn_interval: float = SPAWN_INTERVAL,
    dt: float = DEFAULT_DT,
) -> ValidationResult:
    """Run one concurrent flow test with a global active-ball allowance and no drain phase."""
    import pymunk

    space = pymunk.Space()
    space.gravity = (0, 1800)
    tile = tile_factory()
    registry = TileResourceRegistry.for_space(space)
    builder = TileBuilder(registry, 1, (0, 0))
    result = ValidationResult(name, balls, max_active)
    try:
        tile.build(builder)
    except Exception as error:
        result.runtime_errors.append(_runtime_error(error, 1, "build"))
        return result
    active: list[ValidationBall] = []
    combinations = {port: entry_flow_samples(port) for port in (Port.T0, Port.L0)}
    t = 0.0
    next_spawn = 0.0

    while result.balls_spawned < balls:
        if t + 1e-9 >= next_spawn:
            index = result.balls_spawned
            entry = (Port.T0, Port.L0)[index % 2]
            samples = combinations[entry]
            dx, dy, vx, vy = samples[(index // 2) % len(samples)]
            active.append(_spawn_ball(space, index + 1, entry, t, dx, dy, vx, vy))
            result.balls_spawned += 1
            next_spawn += spawn_interval

        try:
            tile.update(builder, dt)
        except Exception as error:
            result.runtime_errors.append(_runtime_error(error, 1, "update"))
            break
        space.step(dt)
        registry.advance(dt)
        if registry.runtime_errors:
            result.runtime_errors.extend(registry.runtime_errors)
            break
        limit_space_ball_speeds(active)
        t += dt
        _record_trajectories(active, t)
        _classify_active(space, active, result, t)
        result.active = len(active)
        result.peak_active = max(result.peak_active, result.active)
        if result.active > max_active:
            result.capacity_exceeded = True

    # No drain phase: balls still physically inside immediately become the
    # tile's allowed active inventory, whether buffered or merely in transit.
    _classify_active(space, active, result, t)
    result.active = len(active)
    result.peak_active = max(result.peak_active, result.active)
    if result.active > max_active:
        result.capacity_exceeded = True
    for ball in active:
        result.details.append(_detail(ball, "active", None, t))
        _remove_ball(space, ball)
    registry.destroy_owner(1)
    return result


def _runtime_error(error: Exception, owner: int, phase: str) -> dict[str, Any]:
    return {
        "owner": owner,
        "phase": phase,
        "type": type(error).__name__,
        "message": str(error),
        "traceback": "".join(traceback.format_exception(error)),
    }


# Keep the editor-facing name while the API transitions from sampled
# single-ball validation to concurrent aggregate flow validation.
def validate_tile_port_spec(tile_factory: Callable[[], Any], **kwargs) -> ValidationResult:
    kwargs.pop("duration", None)
    return validate_tile_flow(tile_factory, **kwargs)


def _record_trajectories(active: list[ValidationBall], t: float) -> None:
    """Keep compact 20 FPS tracks so failed cases can be replayed in the editor."""
    for ball in active:
        if t + 1e-9 < ball.next_sample_at:
            continue
        ball.trajectory.append([
            round(t - ball.spawned_at, 3),
            round(float(ball.body.position.x), 2),
            round(float(ball.body.position.y), 2),
        ])
        ball.next_sample_at = t + 0.05


def _classify_active(space, active: list[ValidationBall], result: ValidationResult, t: float) -> None:
    for ball in list(active):
        classification = _classify_ball(space, ball)
        if classification is None:
            continue
        status, label = classification
        result.details.append(_detail(ball, status, label, t))
        if status == "exited":
            result.exited += 1
            result.output_counts[label] += 1
        elif status == "lost":
            result.lost += 1
        else:
            result.invalid += 1
        _remove_ball(space, ball)
        active.remove(ball)


def _classify_ball(space, ball: ValidationBall) -> tuple[str, str | None] | None:
    registry = TileResourceRegistry.for_space(space)
    if registry.ball_is_paused(ball.body):
        return None
    if ball.body not in space.bodies or ball.shape not in space.shapes:
        return "lost", "removed"
    x, y = float(ball.body.position.x), float(ball.body.position.y)
    vx, vy = float(ball.body.velocity.x), float(ball.body.velocity.y)
    radius = float(ball.shape.radius)
    if not all(math.isfinite(value) for value in (x, y, vx, vy, radius)):
        return "lost", "non-finite-state"

    # A boundary contact is not an exit: edge geometry may still redirect the
    # ball. Classify only after the ball's complete shape has crossed an edge.
    if y - radius >= TILE_SIZE - BOUNDS_EPSILON:
        return _classify_exit(Port.B0, x, y, vx, vy)
    if x - radius >= TILE_SIZE - BOUNDS_EPSILON:
        return _classify_exit(Port.R0, x, y, vx, vy)
    if y + radius <= BOUNDS_EPSILON:
        return "invalid", "top"
    if x + radius <= BOUNDS_EPSILON:
        return "invalid", "left"
    return None


def _classify_exit(port, x, y, vx, vy):
    spec = PORT_SPECS[port]
    along = x if port == Port.B0 else y
    center = spec.x_center if port == Port.B0 else spec.y_center
    allowed = spec.x_range if port == Port.B0 else spec.y_range
    if abs(along - center) > allowed + BOUNDS_EPSILON:
        return "invalid", _edge_label(port)
    outward = vy if port == Port.B0 else vx
    speed = math.hypot(vx, vy)
    # Full passage proves progress, but the instantaneous velocity must still
    # point outward and stay within 30° of the port normal so the next tile can
    # receive it. A stationary full-passage edge case is accepted.
    if speed > BOUNDS_EPSILON and (
        outward <= 0 or outward / speed + 1e-12 < MAX_EXIT_ANGLE_COSINE
    ):
        return "invalid", f"bad-exit-angle:{port.name}"
    return "exited", port.name


def _edge_label(port):
    if port == Port.B0: return "bottom"
    return "right"


def _spawn_ball(space, ball_id, entry, t, dx, dy, vx, vy) -> ValidationBall:
    import pymunk

    spec = PORT_SPECS[entry]
    if entry == Port.T0:
        position = spec.x_center + dx, spec.y_center + BALL_RADIUS + dy
    elif entry == Port.L0:
        position = spec.x_center + BALL_RADIUS + dx, spec.y_center + dy
    else:
        position = spec.x_center - BALL_RADIUS + dx, spec.y_center + dy
    x = max(BALL_RADIUS + .5, min(TILE_SIZE - BALL_RADIUS - .5, position[0]))
    y = max(BALL_RADIUS + .5, min(TILE_SIZE - BALL_RADIUS - .5, position[1]))
    body = pymunk.Body(BALL_MASS, pymunk.moment_for_circle(BALL_MASS, 0, BALL_RADIUS))
    configure_ball_body(body)
    body.position = x, y
    body.velocity = vx, vy
    shape = pymunk.Circle(body, BALL_RADIUS)
    shape.friction = BALL_FRICTION
    shape.elasticity = BALL_ELASTICITY
    shape.collision_type = BALL_COLLISION_TYPE
    shape.filter = ball_shape_filter()
    space.add(body, shape)
    ball = ValidationBall(ball_id, entry, body, shape, t)
    ball.trajectory.append([0.0, round(x, 2), round(y, 2)])
    ball.next_sample_at = t + 0.05
    return ball


def _failure_message(status, label, x, y, vx, vy):
    if status == "lost":
        return "Ball state was removed or became non-finite."
    if label == "top": return "Ball escaped back through the T0 input."
    if label == "bottom": return "Ball crossed the bottom outside the B0 exit aperture."
    if label == "left": return "Ball crossed the left edge, which has no output port."
    if label == "right": return "Ball crossed the right edge outside the R0 exit aperture."
    if label and label.startswith("bad-exit-angle:"):
        port = label.rsplit(":", 1)[1]
        outward = vy if port == "B0" else vx
        angle = math.degrees(math.acos(max(-1.0, min(1.0, outward / max(math.hypot(vx, vy), 1e-12)))))
        return f"{port} exit angle was {angle:.1f}° from its outward direction (must be ≤ {MAX_EXIT_ANGLE_DEGREES:.0f}°)."
    return "Ball left outside the tile flow contract."


def _detail(ball, status, label, t):
    x, y = float(ball.body.position.x), float(ball.body.position.y)
    vx, vy = float(ball.body.velocity.x), float(ball.body.velocity.y)
    detail = {
        "id": ball.id,
        "entry": ball.entry.name,
        "status": status,
        "exit": label,
        "spawned_at": round(ball.spawned_at, 3),
        "finished_at": round(t, 3),
        "position": [round(x, 2), round(y, 2)],
        "velocity": [round(vx, 2), round(vy, 2)],
        "radius": round(float(ball.shape.radius), 2),
    }
    if status in ("invalid", "lost"):
        if not ball.trajectory or ball.trajectory[-1][1:] != [round(x, 2), round(y, 2)]:
            ball.trajectory.append([round(t - ball.spawned_at, 3), round(x, 2), round(y, 2)])
        detail["message"] = _failure_message(status, label, x, y, vx, vy)
        detail["trajectory"] = ball.trajectory
    return detail


def _remove_ball(space, ball):
    try:
        space.remove(ball.shape, ball.body)
    except Exception:
        pass
