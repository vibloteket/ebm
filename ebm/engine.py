from __future__ import annotations

from dataclasses import dataclass
import math
import random
import time
from typing import Any

from .ball_physics import configure_ball_body, limit_space_ball_speeds
from .ports import BALL_RADIUS, COLUMN_OFFSET, Port, TILE_SIZE, left_neighbor, tile_origin
from .tile_api import BALL_COLLISION_TYPE, BALL_ELASTICITY, BALL_FRICTION, TileBuilder, TileResourceRegistry, ball_shape_filter
from .tile_catalog import default_tile
from .tile_output import suppress_tile_output

BOUNDARY_SPAWN_INTERVAL = 1.2
# One retained tile around the viewport is enough for seamless panning. At
# 0.5×, two tiles added hundreds of unnecessary Pymunk shapes and updates.
BUFFER_TILES = 1
BALL_MASS = 1
PHYSICS_DT = 1 / 60


@dataclass
class Viewport:
    x: float = 0
    y: float = 0
    width: float = 1000
    height: float = 700
    zoom: float = 0.5

    @property
    def right(self) -> float:
        return self.x + self.width / self.zoom

    @property
    def bottom(self) -> float:
        return self.y + self.height / self.zoom


@dataclass
class Ball:
    body: Any
    shape: Any


@dataclass
class ActiveTile:
    tile: Any
    builder: TileBuilder
    owner_id: int


class Engine:
    def __init__(self, width: float = 1000, height: float = 700):
        import pymunk

        self.space = pymunk.Space()
        self.space.gravity = (0, 1800)
        self.viewport = Viewport(-width / (2 * 0.5), -height / (3 * 0.5), width, height, zoom=0.5)
        self.registry = TileResourceRegistry.for_space(self.space)
        self.active_tiles: dict[tuple[int, int], ActiveTile] = {}
        self.balls: list[Ball] = []
        self._next_tile_owner = 1
        self._accumulator = 0.0
        self._rng = random.Random(12345)
        self._initial_seeded = False
        self._spawn_clocks: dict[tuple[int, int, Port], float] = {}
        self.profile: dict[str, dict[str, float]] = {}
        self.reconcile_active_tiles()

    def resize(self, width: float, height: float) -> None:
        self.viewport.width = width
        self.viewport.height = height
        self.reconcile_active_tiles()
        if not self._initial_seeded:
            self.seed_initial_balls()
        self._reconcile_boundary_spawners()

    def pan(self, dx: float, dy: float) -> None:
        self.viewport.x += dx / self.viewport.zoom
        self.viewport.y += dy / self.viewport.zoom
        self.reconcile_active_tiles()
        self._reconcile_boundary_spawners()

    def zoom_at(self, cx: float, cy: float, factor: float) -> None:
        """Zoom in/out keeping (cx, cy) fixed in screen space."""
        self.set_zoom_at(cx, cy, self.viewport.zoom * factor)

    def set_zoom_at(self, cx: float, cy: float, zoom: float) -> None:
        """Set an absolute zoom while keeping a screen point stationary."""
        old = self.viewport.zoom
        new = max(0.2, min(4.0, zoom))
        wx = self.viewport.x + cx / old
        wy = self.viewport.y + cy / old
        self.viewport.zoom = new
        self.viewport.x = wx - cx / new
        self.viewport.y = wy - cy / new
        self.reconcile_active_tiles()
        self._reconcile_boundary_spawners()

    def step_frame(self, dt: float) -> None:
        frame_start = time.perf_counter()

        started = time.perf_counter()
        self.reconcile_active_tiles()
        self._profile_add("tile_reconcile", started)

        started = time.perf_counter()
        for active in list(self.active_tiles.values()):
            with suppress_tile_output():
                active.tile.update(active.builder, min(dt, 0.05))
        self._profile_add("tile_update", started)

        started = time.perf_counter()
        physics_steps = 0
        self._accumulator += min(dt, 0.1)
        while self._accumulator >= PHYSICS_DT:
            self.space.step(PHYSICS_DT)
            self.registry.advance(PHYSICS_DT)
            limit_space_ball_speeds(self.balls)
            self._accumulator -= PHYSICS_DT
            physics_steps += 1
        self._profile_add("physics", started, physics_steps)

        started = time.perf_counter()
        self.maintain_balls(dt)
        self._profile_add("ball_maintenance", started)
        self._profile_add("engine_total", frame_start)

    def _profile_add(self, name: str, started: float, units: int = 1) -> None:
        elapsed_ms = (time.perf_counter() - started) * 1000
        bucket = self.profile.setdefault(name, {"total_ms": 0.0, "calls": 0.0, "max_ms": 0.0, "units": 0.0})
        bucket["total_ms"] += elapsed_ms
        bucket["calls"] += 1
        bucket["max_ms"] = max(bucket["max_ms"], elapsed_ms)
        bucket["units"] += units

    def consume_profile(self) -> dict[str, dict[str, float]]:
        result = self.profile
        self.profile = {}
        return result

    def reconcile_active_tiles(self) -> None:
        needed = self._needed_coords()
        current = set(self.active_tiles)

        for coord in sorted(current - needed):
            active = self.active_tiles.pop(coord)
            self.registry.destroy_owner(active.owner_id)

        for coord in sorted(needed - current):
            row, col = coord
            origin = tile_origin(row, col)
            tile = default_tile()
            owner_id = self._next_tile_owner
            self._next_tile_owner += 1
            builder = TileBuilder(self.registry, owner_id, origin)
            with suppress_tile_output():
                tile.build(builder)
            self.active_tiles[coord] = ActiveTile(tile, builder, owner_id)
            # Camera movement can expose several tile columns before a periodic
            # boundary spawner fires. Seed each newly activated tile
            # immediately so a fast pan never reveals an empty strip.
            if self._initial_seeded:
                self._seed_tile_inputs(row, col)
        if self._initial_seeded:
            self._reconcile_boundary_spawners()

    def _needed_coords(self) -> set[tuple[int, int]]:
        min_col = math.floor(self.viewport.x / TILE_SIZE) - BUFFER_TILES
        max_col = math.floor(self.viewport.right / TILE_SIZE) + BUFFER_TILES
        # Odd columns are shifted down by half a tile.
        min_row = math.floor((self.viewport.y - COLUMN_OFFSET) / TILE_SIZE) - BUFFER_TILES
        max_row = math.floor(self.viewport.bottom / TILE_SIZE) + BUFFER_TILES
        return {
            (row, col)
            for row in range(min_row, max_row + 1)
            for col in range(min_col, max_col + 1)
        }

    def active_bounds(self) -> tuple[float, float, float, float]:
        origins = [tile_origin(row, col) for row, col in self.active_tiles]
        if not origins:
            return self.viewport.x, self.viewport.y, self.viewport.right, self.viewport.bottom
        return (
            min(x for x, _ in origins),
            min(y for _, y in origins),
            max(x for x, _ in origins) + TILE_SIZE,
            max(y for _, y in origins) + TILE_SIZE,
        )

    def seed_initial_balls(self) -> None:
        """Seed one ball at every input of every active buffered tile."""
        if self._initial_seeded:
            return
        self._initial_seeded = True
        for row, col in sorted(self.active_tiles):
            self._seed_tile_inputs(row, col)

    def _seed_tile_inputs(self, row: int, col: int) -> None:
        for port in (Port.T0, Port.L0):
            x, y, velocity = self._port_state(row, col, port)
            if not self._spawn_blocked(x, y):
                self.add_ball(x, y, velocity=velocity)

    def _port_state(self, row: int, col: int, port: Port):
        ox, oy = tile_origin(row, col)
        inset = BALL_RADIUS + 1
        if port == Port.T0:
            return ox + 200, oy + inset, (0, 140)
        return ox + inset, oy + 100, (180, 0)

    def _boundary_inputs(self) -> set[tuple[int, int, Port]]:
        coords = set(self.active_tiles)
        result = set()
        for row, col in coords:
            if (row - 1, col) not in coords:
                result.add((row, col, Port.T0))
            if left_neighbor(row, col) not in coords:
                result.add((row, col, Port.L0))
        return result

    def _reconcile_boundary_spawners(self) -> None:
        boundary = self._boundary_inputs()
        self._spawn_clocks = {
            key: value for key, value in self._spawn_clocks.items() if key in boundary
        }
        for row, col, port in boundary:
            key = (row, col, port)
            if key not in self._spawn_clocks:
                # Stable phase avoids a synchronized burst around the border.
                phase = ((row * 37 + col * 61 + port.value[0] * 3 + port.value[1]) % 100) / 100
                self._spawn_clocks[key] = BOUNDARY_SPAWN_INTERVAL * (0.35 + phase)

    def maintain_balls(self, dt: float) -> None:
        if not self._initial_seeded:
            return
        left, top, right, bottom = self.active_bounds()
        for ball in list(self.balls):
            x, y = ball.body.position
            if x < left or x > right or y < top or y > bottom:
                self.remove_ball(ball)

        for key in list(self._spawn_clocks):
            self._spawn_clocks[key] -= dt
            if self._spawn_clocks[key] <= 0:
                row, col, port = key
                x, y, velocity = self._port_state(row, col, port)
                if not self._spawn_blocked(x, y):
                    self.add_ball(x, y, velocity=velocity)
                self._spawn_clocks[key] += BOUNDARY_SPAWN_INTERVAL

    def _spawn_blocked(self, x: float, y: float) -> bool:
        minimum = (BALL_RADIUS * 2.25) ** 2
        return any(
            (float(ball.body.position.x) - x) ** 2 + (float(ball.body.position.y) - y) ** 2 < minimum
            for ball in self.balls
        )

    def add_ball(self, x: float, y: float, velocity: tuple[float, float] | None = None) -> Ball:
        import pymunk

        moment = pymunk.moment_for_circle(BALL_MASS, 0, BALL_RADIUS)
        body = pymunk.Body(BALL_MASS, moment)
        configure_ball_body(body)
        body.position = (x, y)
        body.velocity = velocity if velocity is not None else (self._rng.uniform(-80, 80), self._rng.uniform(-20, 80))
        body.sketch_seed = self._rng.randint(1, 999_999)
        shape = pymunk.Circle(body, BALL_RADIUS)
        shape.friction = BALL_FRICTION
        shape.elasticity = BALL_ELASTICITY
        shape.ebm_fill_color = (22, 114, 212, 255)
        shape.ebm_stroke_color = (12, 63, 143, 255)
        shape.collision_type = BALL_COLLISION_TYPE
        shape.filter = ball_shape_filter()
        self.space.add(body, shape)
        ball = Ball(body, shape)
        self.balls.append(ball)
        return ball

    def remove_ball(self, ball: Ball) -> None:
        try:
            self.space.remove(ball.shape, ball.body)
        except Exception:
            pass
        try:
            self.balls.remove(ball)
        except ValueError:
            pass

    def screen_to_world(self, x: float, y: float) -> tuple[float, float]:
        return self.viewport.x + x / self.viewport.zoom, self.viewport.y + y / self.viewport.zoom
