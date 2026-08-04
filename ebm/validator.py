from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Callable

from .ports import OUTPUT_PORTS, PORT_SPECS, Port
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
DEFAULT_DT = 1 / 120
VALIDATION_BALLS = 120
MAX_ACTIVE_BALLS = 20
SPAWN_INTERVAL = 0.4
EXIT_TOLERANCE = 28
EXIT_SPEED = 20
BOUNDS_EPSILON = 0.25


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
    space.gravity = (0, 900)
    tile = tile_factory()
    registry = TileResourceRegistry.for_space(space)
    builder = TileBuilder(registry, 1, (0, 0))
    tile.build(builder)
    result = ValidationResult(name, balls, max_active)
    active: list[ValidationBall] = []
    combinations = {port: PORT_SPECS[port].sample_values()[1] for port in (Port.T0, Port.L0, Port.R0)}
    t = 0.0
    next_spawn = 0.0

    while result.balls_spawned < balls:
        if t + 1e-9 >= next_spawn:
            index = result.balls_spawned
            entry = (Port.T0, Port.L0, Port.R0)[index % 3]
            samples = combinations[entry]
            dx, dy, dvx, dvy = samples[(index // 3) % len(samples)]
            active.append(_spawn_ball(space, index + 1, entry, t, dx, dy, dvx, dvy))
            result.balls_spawned += 1
            next_spawn += spawn_interval

        tile.update(builder, dt)
        space.step(dt)
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
    if ball.body not in space.bodies or ball.shape not in space.shapes:
        return "lost", "removed"
    x, y = float(ball.body.position.x), float(ball.body.position.y)
    vx, vy = float(ball.body.velocity.x), float(ball.body.velocity.y)
    if not all(math.isfinite(value) for value in (x, y, vx, vy)):
        return "lost", "non-finite-state"
    for port in (Port.B0, Port.L1, Port.R1):
        if _in_exit_aperture(port, x, y, vx, vy):
            if _satisfies_exit_spec(port, PORT_SPECS[port], x, y, vx, vy):
                return "exited", port.name
            return "invalid", f"bad-exit-spec:{port.name}"
    if not _ball_fully_inside_tile(x, y):
        return "invalid", _bounds_label(x, y)
    return None


def _spawn_ball(space, ball_id, entry, t, dx, dy, dvx, dvy) -> ValidationBall:
    import pymunk

    spec = PORT_SPECS[entry]
    base_vx, base_vy = _entry_base_velocity(entry)
    if entry == Port.T0:
        position = spec.x_center + dx, spec.y_center + BALL_RADIUS + dy
    elif entry == Port.L0:
        position = spec.x_center + BALL_RADIUS + dx, spec.y_center + dy
    else:
        position = spec.x_center - BALL_RADIUS + dx, spec.y_center + dy
    x = max(BALL_RADIUS + .5, min(200 - BALL_RADIUS - .5, position[0]))
    y = max(BALL_RADIUS + .5, min(200 - BALL_RADIUS - .5, position[1]))
    body = pymunk.Body(BALL_MASS, pymunk.moment_for_circle(BALL_MASS, 0, BALL_RADIUS))
    body.position = x, y
    body.velocity = base_vx + dvx, base_vy + dvy
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


def _entry_base_velocity(entry: Port) -> tuple[float, float]:
    if entry == Port.T0: return 0, 70
    if entry == Port.L0: return 110, 0
    return -110, 0


def _in_exit_aperture(port, x, y, vx, vy) -> bool:
    if not _ball_fully_inside_tile(x, y): return False
    if port == Port.B0: return abs(x - 100) <= EXIT_TOLERANCE and y >= 200 - BALL_RADIUS - 2 and vy >= EXIT_SPEED
    if port == Port.L1: return x <= BALL_RADIUS + 2 and abs(y - 150) <= EXIT_TOLERANCE and vx <= -EXIT_SPEED
    return x >= 200 - BALL_RADIUS - 2 and abs(y - 50) <= EXIT_TOLERANCE and vx >= EXIT_SPEED


def _satisfies_exit_spec(port, spec, x, y, vx, vy) -> bool:
    if abs(x - spec.x_center) > spec.x_range + EXIT_TOLERANCE or abs(y - spec.y_center) > spec.y_range + EXIT_TOLERANCE: return False
    if port == Port.B0: return vy >= spec.vy_min
    if port == Port.L1: return vx <= -spec.vx_min and abs(vy) <= spec.exit_vy_range
    return vx >= spec.vx_min and abs(vy) <= spec.exit_vy_range


def _ball_fully_inside_tile(x, y) -> bool:
    return BALL_RADIUS - BOUNDS_EPSILON <= x <= 200 - BALL_RADIUS + BOUNDS_EPSILON and BALL_RADIUS - BOUNDS_EPSILON <= y <= 200 - BALL_RADIUS + BOUNDS_EPSILON


def _bounds_label(x, y) -> str:
    if y < BALL_RADIUS - BOUNDS_EPSILON: return "top"
    if y > 200 - BALL_RADIUS + BOUNDS_EPSILON: return "bottom"
    if x < BALL_RADIUS - BOUNDS_EPSILON: return "left"
    if x > 200 - BALL_RADIUS + BOUNDS_EPSILON: return "right"
    return "bounds"


def _failure_message(status, label, x, y, vx, vy):
    if status == "lost":
        return "Ball state was removed or became non-finite."
    if label == "top": return "Ball escaped back through the T0 input."
    if label == "bottom": return "Ball crossed the bottom outside the B0 exit aperture."
    if label == "left": return "Ball crossed the left edge outside the L1 exit aperture."
    if label == "right": return "Ball crossed the right edge outside the R1 exit aperture."
    if label == "bad-exit-spec:B0":
        return f"B0 requires downward velocity vy ≥ 40; this ball had vy={vy:.1f}."
    if label == "bad-exit-spec:L1":
        problems = []
        if vx > -40: problems.append(f"vx={vx:.1f} (must be ≤ -40)")
        if abs(vy) > 200: problems.append(f"|vy|={abs(vy):.1f} (must be ≤ 200)")
        return "L1 exit velocity was outside contract: " + ", ".join(problems or [f"vx={vx:.1f}, vy={vy:.1f}"])
    if label == "bad-exit-spec:R1":
        problems = []
        if vx < 40: problems.append(f"vx={vx:.1f} (must be ≥ 40)")
        if abs(vy) > 200: problems.append(f"|vy|={abs(vy):.1f} (must be ≤ 200)")
        return "R1 exit velocity was outside contract: " + ", ".join(problems or [f"vx={vx:.1f}, vy={vy:.1f}"])
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
