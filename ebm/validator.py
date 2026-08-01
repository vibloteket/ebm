from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from typing import Any, Callable

from .ports import Port, PORT_SPECS, PortSpec, MIRROR_PORT, RoutePermutation
from .routes import ALL_ROUTES, DEFAULT_ROUTES
from .tile_api import BALL_COLLISION_TYPE, BALL_ELASTICITY, BALL_FRICTION, TileBuilder, TileResourceRegistry, ball_shape_filter
from .tile_catalog import tile_for_route
from .tiles import ReferenceRouterTile

BALL_RADIUS = 8
BALL_MASS = 1
DEFAULT_DURATION = 12.0
DEFAULT_DT = 1 / 240
DEFAULT_BALLS_PER_ENTRY = 6
DEFAULT_SPAWN_INTERVAL = 0.55
EXIT_TOLERANCE = 28
EXIT_SPEED = 20
# The complete ball must remain inside the tile. Exits are detected only in a
# small inside-the-border aperture, while the ball is moving outward. This
# avoids counting a ball stuck near an exit marker as successful.
BOUNDS_EPSILON = 0.25
STUCK_SPEED = 6
STUCK_AFTER = 3.0
# Validation should simulate realistic handoff noise from the previous tile:
# balls may arrive slightly offset from the ghost port and with a velocity that
# is not perfectly aligned with the nominal entry direction.
SPAWN_VARIATIONS = (
    (0.0, 0.0),
    (-6.0, -25.0),
    (6.0, 25.0),
    (-10.0, 15.0),
    (10.0, -15.0),
    (0.0, 35.0),
)


@dataclass
class ValidationBall:
    id: int
    entry: Port
    body: Any
    shape: Any
    spawned_at: float
    status: str = "active"
    exit: str | None = None
    finished_at: float | None = None
    slow_since: float | None = None


@dataclass
class ValidationResult:
    name: str
    route: RoutePermutation
    duration: float
    balls_spawned: int = 0
    exited: int = 0
    unexpected: int = 0
    out_of_bounds: int = 0
    stuck: int = 0
    active: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (
            self.unexpected == 0
            and self.out_of_bounds == 0
            and self.stuck == 0
            and self.exited == self.balls_spawned
        )

    @property
    def pass_ratio(self) -> float:
        if self.balls_spawned == 0:
            return 0.0
        return self.exited / self.balls_spawned

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "route": {
                "entries": [p.name for p in self.route.entries],
                "exits": [p.name for p in self.route.exits],
                "label": route_label(self.route),
            },
            "duration": self.duration,
            "balls_spawned": self.balls_spawned,
            "exited": self.exited,
            "unexpected": self.unexpected,
            "out_of_bounds": self.out_of_bounds,
            "stuck": self.stuck,
            "active": self.active,
            "pass_ratio": self.pass_ratio,
            "ok": self.ok,
            "details": self.details,
        }

    def summary(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        return (
            f"{status} {self.name}: {self.exited}/{self.balls_spawned} exited, "
            f"{self.unexpected} unexpected, {self.out_of_bounds} out-of-bounds, "
            f"{self.stuck} stuck, {self.active} active"
        )


def route_label(route: RoutePermutation) -> str:
    entries = ",".join(p.name for p in route.entries)
    exits = ",".join(p.name for p in route.exits)
    return f"{entries} -> {exits}"


def validate_filler_route(
    route: RoutePermutation,
    *,
    duration: float = DEFAULT_DURATION,
    balls_per_entry: int = DEFAULT_BALLS_PER_ENTRY,
    spawn_interval: float = DEFAULT_SPAWN_INTERVAL,
) -> ValidationResult:
    return validate_tile(
        lambda: tile_for_route(route),
        route,
        name=f"filler {route_label(route)}",
        duration=duration,
        balls_per_entry=balls_per_entry,
        spawn_interval=spawn_interval,
    )


def validate_filler_route_port_spec(
    route: RoutePermutation,
    *,
    duration: float = 16.0,
    dt: float = DEFAULT_DT,
) -> ValidationResult:
    return validate_tile_port_spec(
        lambda: tile_for_route(route),
        route,
        name=f"filler {route_label(route)} (port-spec)",
        duration=duration,
        dt=dt,
    )


def validate_tile_port_spec(
    tile_factory: Callable[[], Any],
    route: RoutePermutation,
    *,
    name: str = "tile (port-spec)",
    duration: float = 16.0,
    dt: float = DEFAULT_DT,
) -> ValidationResult:
    """Validate every sampled entry state against an exact route mapping."""
    import pymunk

    space = pymunk.Space()
    space.gravity = (0, 900)
    tile = tile_factory()
    ctx = TileBuilder(TileResourceRegistry.for_space(space), 1, (0, 0))
    tile.build(ctx)

    result = ValidationResult(name=name, route=route, duration=duration)

    for entry in route.entries:
        spec = PORT_SPECS[entry]
        ranges, combos = spec.sample_values()
        xs, ys, vxs, vys = ranges

        for dx, dy, dvx, dvy in combos:
            # Base velocity points *into* the tile.
            base_vx, base_vy = _entry_base_velocity(entry)

            # Spawn one ball-radius inside the tile border so the full ball is
            # inside at t=0, then add the spec offset on top.  Clamp to the
            # physical tile interior so that even the worst-case offsets start
            # legally.
            if entry == Port.T0:
                px = spec.x_center + dx
                py = spec.y_center + BALL_RADIUS + dy
                # Clamp inside tile
                px = max(BALL_RADIUS + 0.5, min(200 - BALL_RADIUS - 0.5, px))
                py = max(BALL_RADIUS + 0.5, min(200 - BALL_RADIUS - 0.5, py))
            elif entry == Port.L0:
                px = spec.x_center + BALL_RADIUS + dx
                py = spec.y_center + dy
                px = max(BALL_RADIUS + 0.5, min(200 - BALL_RADIUS - 0.5, px))
                py = max(BALL_RADIUS + 0.5, min(200 - BALL_RADIUS - 0.5, py))
            elif entry == Port.R0:
                px = spec.x_center - BALL_RADIUS + dx
                py = spec.y_center + dy
                px = max(BALL_RADIUS + 0.5, min(200 - BALL_RADIUS - 0.5, px))
                py = max(BALL_RADIUS + 0.5, min(200 - BALL_RADIUS - 0.5, py))
            else:
                px = spec.x_center + dx
                py = spec.y_center + dy
                px = max(BALL_RADIUS + 0.5, min(200 - BALL_RADIUS - 0.5, px))
                py = max(BALL_RADIUS + 0.5, min(200 - BALL_RADIUS - 0.5, py))

            vx = base_vx + dvx
            vy = base_vy + dvy

            moment = pymunk.moment_for_circle(BALL_MASS, 0, BALL_RADIUS)
            body = pymunk.Body(BALL_MASS, moment)
            body.position = (px, py)
            body.velocity = (vx, vy)
            shape = pymunk.Circle(body, BALL_RADIUS)
            shape.friction = BALL_FRICTION
            shape.elasticity = BALL_ELASTICITY
            shape.collision_type = BALL_COLLISION_TYPE
            shape.filter = ball_shape_filter()
            space.add(body, shape)
            ball = ValidationBall(
                id=0,
                entry=entry,
                body=body,
                shape=shape,
                spawned_at=0.0,
            )
            result.balls_spawned += 1

            t = 0.0
            done = False
            steps = int(duration / dt)
            for _step in range(steps):
                if done:
                    break
                tile.update(ctx, dt)
                space.step(dt)
                t += dt

                if ball.status != "active":
                    continue

                classification = _classify_ball(ball.body.position, ball.body.velocity, route)
                if classification is not None:
                    pass  # unpack below
                elif _is_slow_inside(ball):
                    if ball.slow_since is None:
                        ball.slow_since = t
                    elif t - ball.slow_since >= STUCK_AFTER:
                        classification = ("stuck", "settled")
                else:
                    ball.slow_since = None

                if classification is None:
                    continue

                status, exit_name = classification
                if status == "exited" and exit_name is not None:
                    # A permutation route maps entries to exits by position.
                    # Passing through another declared output is not success.
                    # Legacy two-flow routes historically declared a set of
                    # acceptable outputs. Uniform 3x3 permutations explicitly
                    # declare a bijective entry-to-exit mapping by position.
                    expected_exit = route.exit_for(entry)
                    if exit_name != expected_exit.name:
                            status = "unexpected"
                            exit_name = f"wrong-route:{exit_name}:expected-{expected_exit.name}"

                if status == "exited" and exit_name is not None:
                    # Verify exit spec
                    exit_port = Port[exit_name]
                    exit_spec = PORT_SPECS.get(exit_port)
                    if exit_spec is not None:
                        ex, ey = float(ball.body.position.x), float(ball.body.position.y)
                        evx, evy = float(ball.body.velocity.x), float(ball.body.velocity.y)
                        if not _satisfies_exit_spec(exit_port, exit_spec, ex, ey, evx, evy):
                            status = "unexpected"
                            exit_name = f"bad-exit-spec:{exit_name}"

                ball.status = status
                ball.exit = exit_name
                ball.finished_at = t
                result.details.append({
                    "entry": entry.name,
                    "dx": dx, "dy": dy, "dvx": dvx, "dvy": dvy,
                    "status": status,
                    "exit": exit_name,
                    "finish_pos": [round(float(ball.body.position.x), 2), round(float(ball.body.position.y), 2)],
                    "finish_vel": [round(float(ball.body.velocity.x), 2), round(float(ball.body.velocity.y), 2)],
                })
                _remove_ball(space, ball)
                done = True

            if not done:
                ball.status = "active"
                ball.finished_at = duration
                result.details.append({
                    "entry": entry.name,
                    "dx": dx, "dy": dy, "dvx": dvx, "dvy": dvy,
                    "status": "active",
                    "finish_pos": [round(float(ball.body.position.x), 2), round(float(ball.body.position.y), 2)],
                })
                _remove_ball(space, ball)

    result.exited = sum(1 for d in result.details if d.get("status") == "exited")
    result.unexpected = sum(1 for d in result.details if d.get("status") == "unexpected")
    result.out_of_bounds = sum(1 for d in result.details if d.get("status") == "out_of_bounds")
    result.stuck = sum(1 for d in result.details if d.get("status") == "stuck")
    result.active = sum(1 for d in result.details if d.get("status") == "active")

    TileResourceRegistry.for_space(space).destroy_owner(1)
    return result


def validate_all_fillers(
    *,
    duration: float = DEFAULT_DURATION,
    balls_per_entry: int = DEFAULT_BALLS_PER_ENTRY,
    spawn_interval: float = DEFAULT_SPAWN_INTERVAL,
) -> list[ValidationResult]:
    return [
        validate_filler_route(
            route,
            duration=duration,
            balls_per_entry=balls_per_entry,
            spawn_interval=spawn_interval,
        )
        for route in ALL_ROUTES
    ]


def validate_all_fillers_port_spec(
    *,
    duration: float = 16.0,
    dt: float = DEFAULT_DT,
) -> list[ValidationResult]:
    return [
        validate_filler_route_port_spec(route, duration=duration, dt=dt)
        for route in ALL_ROUTES
    ]


def validate_tile(
    tile_factory: Callable[[], Any],
    route: RoutePermutation,
    *,
    name: str = "tile",
    duration: float = DEFAULT_DURATION,
    balls_per_entry: int = DEFAULT_BALLS_PER_ENTRY,
    spawn_interval: float = DEFAULT_SPAWN_INTERVAL,
) -> ValidationResult:
    import pymunk

    space = pymunk.Space()
    space.gravity = (0, 900)
    tile = tile_factory()
    ctx = TileBuilder(TileResourceRegistry.for_space(space), 1, (0, 0))
    tile.build(ctx)

    result = ValidationResult(name=name, route=route, duration=duration)
    balls: list[ValidationBall] = []
    next_id = 1
    next_spawn = 0.0
    spawned_batches = 0
    t = 0.0
    steps = int(duration / DEFAULT_DT)

    for _ in range(steps):
        if spawned_batches < balls_per_entry and t >= next_spawn:
            for entry in route.entries:
                variation = SPAWN_VARIATIONS[spawned_batches % len(SPAWN_VARIATIONS)]
                ball = _spawn_ball(space, next_id, entry, t, variation)
                next_id += 1
                balls.append(ball)
                result.balls_spawned += 1
            spawned_batches += 1
            next_spawn += spawn_interval

        tile.update(ctx, DEFAULT_DT)
        space.step(DEFAULT_DT)
        t += DEFAULT_DT

        for ball in balls:
            if ball.status != "active":
                continue
            classification = _classify_ball(ball.body.position, ball.body.velocity, route)
            if classification is None:
                if _is_slow_inside(ball):
                    if ball.slow_since is None:
                        ball.slow_since = t
                        continue
                    elif t - ball.slow_since >= STUCK_AFTER:
                        classification = ("stuck", "settled")
                    else:
                        continue
                else:
                    ball.slow_since = None
                    continue
            status, exit_name = classification
            ball.status = status
            ball.exit = exit_name
            ball.finished_at = t
            result.details.append(_ball_detail(ball))
            _remove_ball(space, ball)

    for ball in balls:
        if ball.status == "active":
            speed = ball.body.velocity.length
            ball.status = "stuck" if speed < STUCK_SPEED or _inside_tile(ball.body.position) else "active"
            ball.finished_at = duration
            result.details.append(_ball_detail(ball))
            _remove_ball(space, ball)

    result.exited = sum(1 for b in balls if b.status == "exited")
    result.unexpected = sum(1 for b in balls if b.status == "unexpected")
    result.out_of_bounds = sum(1 for b in balls if b.status == "out_of_bounds")
    result.stuck = sum(1 for b in balls if b.status == "stuck")
    result.active = sum(1 for b in balls if b.status == "active")
    TileResourceRegistry.for_space(space).destroy_owner(1)
    return result


def results_to_json(results: list[ValidationResult]) -> str:
    return json.dumps([result.to_dict() for result in results], indent=2)


def _entry_base_velocity(entry: Port) -> tuple[float, float]:
    if entry == Port.T0:
        return (0, 70)
    if entry == Port.L0:
        return (110, 0)
    if entry == Port.R0:
        return (-110, 0)
    return (0, 0)


def _spawn_ball(
    space,
    ball_id: int,
    entry: Port,
    t: float,
    variation: tuple[float, float] = (0.0, 0.0),
) -> ValidationBall:
    import pymunk

    offset, skew = variation
    x, y = entry.point
    if entry == Port.T0:
        # Previous tile's B0 output should usually be downward, but not
        # perfectly centered or perfectly vertical.
        pos = (x + offset, y + BALL_RADIUS)
        vel = (skew, 70)
    elif entry == Port.L0:
        # Previous tile's R1 output enters from the left. It may be a bit above
        # or below L0 and may have residual vertical velocity.
        pos = (x + BALL_RADIUS + 2, y + offset)
        vel = (110, skew)
    elif entry == Port.R0:
        # Previous tile's L1 output enters from the right.
        pos = (x - BALL_RADIUS - 2, y + offset)
        vel = (-110, skew)
    else:
        pos = (x, y)
        vel = (0, 0)

    moment = pymunk.moment_for_circle(BALL_MASS, 0, BALL_RADIUS)
    body = pymunk.Body(BALL_MASS, moment)
    body.position = pos
    body.velocity = vel
    shape = pymunk.Circle(body, BALL_RADIUS)
    shape.friction = BALL_FRICTION
    shape.elasticity = BALL_ELASTICITY
    shape.collision_type = BALL_COLLISION_TYPE
    shape.filter = ball_shape_filter()
    space.add(body, shape)
    return ValidationBall(ball_id, entry, body, shape, t)


def _satisfies_exit_spec(port: Port, spec: PortSpec, x: float, y: float, vx: float, vy: float) -> bool:
    if not (abs(x - spec.x_center) <= spec.x_range + EXIT_TOLERANCE):
        return False
    if not (abs(y - spec.y_center) <= spec.y_range + EXIT_TOLERANCE):
        return False
    if port in (Port.B0, Port.T0):
        # Vertical ports: ball must be moving downward.  We deliberately do
        # *not* constrain vx here — the next tile's entry spec handles side
        # velocity.
        if vy < spec.vy_min:
            return False
    elif port in (Port.L0, Port.L1):
        if vx > -spec.vx_min:
            return False
        if abs(vy) > spec.exit_vy_range:
            return False
    elif port in (Port.R0, Port.R1):
        if vx < spec.vx_min:
            return False
        if abs(vy) > spec.exit_vy_range:
            return False
    return True



def _is_slow_inside(ball: ValidationBall) -> bool:
    return ball.body.velocity.length < STUCK_SPEED and _inside_tile(ball.body.position)

def _remove_ball(space, ball: ValidationBall) -> None:
    try:
        space.remove(ball.shape, ball.body)
    except Exception:
        pass


def _classify_ball(pos, vel, route: RoutePermutation) -> tuple[str, str] | None:
    x, y = float(pos.x), float(pos.y)
    vx, vy = float(vel.x), float(vel.y)

    # Success is detected before the ball crosses the border: the full ball is
    # still inside the tile, inside a small exit aperture, and moving outward.
    exit_port = _matching_exit_inside_tile(x, y, vx, vy, route)
    if exit_port is not None:
        return "exited", exit_port.name

    # Reaching a non-declared output aperture is an unexpected exit.
    for port in (Port.B0, Port.L1, Port.R1):
        if _in_exit_aperture(port, x, y, vx, vy):
            return "unexpected", port.name

    # Hard validation: no part of the ball may leave the tile bounds at any
    # time. This catches bounce-ups above the tile and side-border scraping.
    if not _ball_fully_inside_tile(x, y):
        return "out_of_bounds", _bounds_label(x, y)
    return None


def _matching_exit_inside_tile(x: float, y: float, vx: float, vy: float, route: RoutePermutation) -> Port | None:
    for port in route.exits:
        if _in_exit_aperture(port, x, y, vx, vy):
            return port
    return None


def _in_exit_aperture(port: Port, x: float, y: float, vx: float, vy: float) -> bool:
    px, py = _inside_exit_point(port)
    if not _ball_fully_inside_tile(x, y):
        return False
    if port == Port.B0:
        return abs(x - px) <= EXIT_TOLERANCE and y >= py - 2 and vy >= EXIT_SPEED
    if port == Port.L1:
        return x <= px + 2 and abs(y - py) <= EXIT_TOLERANCE and vx <= -EXIT_SPEED
    if port == Port.R1:
        return x >= px - 2 and abs(y - py) <= EXIT_TOLERANCE and vx >= EXIT_SPEED
    return False


def _inside_exit_point(port: Port) -> tuple[float, float]:
    x, y = port.point
    if port == Port.B0:
        return x, y - BALL_RADIUS
    if port == Port.L1:
        return x + BALL_RADIUS, y
    if port == Port.R1:
        return x - BALL_RADIUS, y
    return x, y


def _ball_fully_inside_tile(x: float, y: float) -> bool:
    return (
        BALL_RADIUS - BOUNDS_EPSILON <= x <= 200 - BALL_RADIUS + BOUNDS_EPSILON
        and BALL_RADIUS - BOUNDS_EPSILON <= y <= 200 - BALL_RADIUS + BOUNDS_EPSILON
    )


def _bounds_label(x: float, y: float) -> str:
    if y < BALL_RADIUS - BOUNDS_EPSILON:
        return "top"
    if y > 200 - BALL_RADIUS + BOUNDS_EPSILON:
        return "bottom"
    if x < BALL_RADIUS - BOUNDS_EPSILON:
        return "left"
    if x > 200 - BALL_RADIUS + BOUNDS_EPSILON:
        return "right"
    return "bounds"


def _inside_tile(pos) -> bool:
    return _ball_fully_inside_tile(float(pos.x), float(pos.y))


def _ball_detail(ball: ValidationBall) -> dict[str, Any]:
    return {
        "id": ball.id,
        "entry": ball.entry.name,
        "status": ball.status,
        "exit": ball.exit,
        "spawned_at": round(ball.spawned_at, 3),
        "finished_at": None if ball.finished_at is None else round(ball.finished_at, 3),
        "position": [round(float(ball.body.position.x), 2), round(float(ball.body.position.y), 2)],
        "speed": round(float(ball.body.velocity.length), 2),
    }
