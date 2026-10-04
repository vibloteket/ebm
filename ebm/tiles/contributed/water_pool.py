from __future__ import annotations

import math

from ebm import TileBase, TileBuilder

# A wide open pool catches every incoming ball: T0 drops straight in, L0
# arcs in over the low left rim (a slope guides even the slowest entries
# in). The water is a foreground polygon drawn after the balls, so sinking
# balls are occluded; they also fade out by depth and are then paused into
# an invisible stockpile. The "dissolve" is pure occlusion plus alpha — the
# ball count is conserved 1:1.
#
# Two visual-only pipes (one per output) carry animated water dashes from
# the pool to two fill boxes. The boxes alternate strictly: the pipe runs,
# the box fills, the tap closes, the water crossfades into a stockpiled
# ball (the water is the same blue as the balls, so the illusion holds),
# and a hatch/gate releases it to the output. No ball ever travels a pipe —
# the move happens while the ball is paused and invisible.
#
# Throughput: one box cycle is ~1.5 s, so the alternating pair sustains
# ~1.4 balls/s against the 0.8 balls/s nominal supply; the stockpile stays
# well within the validator's 20-ball active capacity (paused balls count
# as active there).

WATER_TOP = 150.0
POOL_FLOOR = 215.0
POOL_RIGHT = 328.0
RIM_TOP = 40.0  # The right wall runs high: fast L0 flyovers cannot pass.

CAPTURE_TOP = 165.0     # Below this depth the fade starts.
CAPTURE_BOTTOM = 194.0  # Fully dissolved: pause into the stockpile.
WATER_DRAG = 0.80       # Velocity keep-factor per 120 Hz frame; sinks ~75 u/s.

FLOW_SECONDS = 0.45
CONDENSE_SECONDS = 0.45
RECOVER_SECONDS = 0.10
B0_RELEASE_SECONDS = 0.35
R0_RELEASE_TIMEOUT = 0.70
R0_GATE_CLEAR_X = 413.0
EXIT_VX = 340.0
DASHES_PER_PIPE = 3

# B0: pipe drops from the pool floor into an open-topped crate whose floor
# is a pausable hatch (same release pattern as the laser turret's B0 box).
B0_PIPE_X = 200.0
B0_PIPE_BOTTOM = 340.0
B0_BOX_LEFT = 178.0
B0_BOX_RIGHT = 222.0
B0_BOX_TOP = 345.0
B0_HATCH_Y = 388.0
B0_SPAWN = (200.0, 370.0)
B0_FILL_BOTTOM = 368.0
B0_FILL_HEIGHT = 23.0
B0_FILL_RADIUS = 17.0

# R0: pipe leaves the pool wall, turns down, and enters the ceiling of a
# crate just left of R0. A pausable gate holds the ball while it forms;
# the conveyor floor plus an exit-speed kick carry it through the band.
R0_PIPE_Y = 183.0
R0_PIPE_X = 368.0
R0_PIPE_BOTTOM = 266.0
R0_BOX_LEFT = 348.0
R0_CEIL_Y = 272.0
R0_FLOOR_Y = 330.0
R0_GATE_X = 393.0
R0_SPAWN = (368.0, 311.0)
R0_FILL_X = 368.0
R0_FILL_BOTTOM = 310.0
R0_FILL_HEIGHT = 22.0
R0_FILL_RADIUS = 17.0

SPLASH_SECONDS = 0.30
SPLASH_RAYS = 5

BALL_FILL = (22, 114, 212, 255)
BALL_STROKE = (12, 63, 143, 255)
WATER = (22, 114, 212, 190)
NO_WATER = (22, 114, 212, 0)
SURFACE = (130, 190, 255, 230)
PIPE = (49, 90, 168, 255)
CRATE = (115, 76, 168, 255)
MECH = (220, 140, 35, 255)
NO_MECH = (220, 140, 35, 0)
DASH = (185, 220, 255, 235)
NO_DASH = (185, 220, 255, 0)
SPLASH = (170, 210, 255, 230)
NO_SPLASH = (170, 210, 255, 0)


class WaterPool(TileBase):
    """Balls splash into a pool and dissolve; pipe water fills two small
    boxes that condense the water back into balls at B0 and R0, strictly
    alternating."""

    author = "Pi"
    enabled = False  # Editor-only until the user asks to enable.

    def build(self, b: TileBuilder) -> None:
        self.stockpile = []
        self.sinking = set()
        self.restore_colors = []
        self.next_box = "b0"
        self.splash_t = 0.0
        self.splash_center = (200.0, WATER_TOP)

        # The basin. The left rim sits below the L0 band with a slope so
        # even near-stationary entries roll in; the right wall runs to
        # RIM_TOP so even a 600 u/s L0 ball cannot fly over the pool (it
        # crosses the wall plane around y~190 and falls back in).
        b.static_segment((4.0, WATER_TOP), (4.0, POOL_FLOOR), 4,
                         friction=0.2, elasticity=0.05, fill_color=PIPE)
        b.static_segment((4.0, WATER_TOP), (28.0, 170.0), 4,
                         friction=0.2, elasticity=0.05, fill_color=PIPE)
        b.static_segment((POOL_RIGHT, RIM_TOP), (POOL_RIGHT, POOL_FLOOR), 4,
                         friction=0.2, elasticity=0.05, fill_color=PIPE)
        b.static_segment((4.0, POOL_FLOOR), (POOL_RIGHT, POOL_FLOOR), 4,
                         friction=0.3, elasticity=0.05, fill_color=PIPE)

        # The water: a foreground polygon occludes submerged balls; a light
        # line marks the surface.
        b.visual_polygon(
            ((8.0, WATER_TOP), (POOL_RIGHT - 4, WATER_TOP),
             (POOL_RIGHT - 4, POOL_FLOOR), (8.0, POOL_FLOOR)),
            fill_color=WATER, stroke_color=WATER, foreground=True)
        b.visual_segment((8.0, WATER_TOP), (POOL_RIGHT - 4, WATER_TOP), 2,
                         fill_color=SURFACE, stroke_color=SURFACE, foreground=True)

        sensor = b.sensor_box(10.0, WATER_TOP + 2, POOL_RIGHT - 4, 211.0)

        def enter(event):
            ball = event.ball
            if ball in self.sinking:
                return
            self.sinking.add(ball)
            try:
                _, vy = ball.velocity
                x, _ = ball.position
            except PermissionError:
                return
            if vy > 150:
                self.splash_t = SPLASH_SECONDS
                self.splash_center = (min(max(x, 40.0), 296.0), WATER_TOP)

        def leave(event):
            ball = event.ball
            if ball in self.sinking:
                self.sinking.discard(ball)
                # Bounced out mid-fade: restore full color so no ghost ball
                # is left rolling around. Deferred: style writes inside
                # contact callbacks are unsafe.
                self.restore_colors.append(ball)

        b.on_ball_contact(sensor, begin=enter, separate=leave)

        # B0 pipe: two vertical walls from the pool floor to the crate top.
        b.visual_segment((190.0, POOL_FLOOR - 2), (190.0, B0_PIPE_BOTTOM), 3,
                         fill_color=PIPE, stroke_color=PIPE)
        b.visual_segment((210.0, POOL_FLOOR - 2), (210.0, B0_PIPE_BOTTOM), 3,
                         fill_color=PIPE, stroke_color=PIPE)
        # B0 crate: open top, pausable hatch floor.
        b.static_segment((B0_BOX_LEFT, B0_BOX_TOP), (B0_BOX_LEFT, 391.0), 3,
                         friction=0.1, elasticity=0.05, fill_color=CRATE)
        b.static_segment((B0_BOX_RIGHT, B0_BOX_TOP), (B0_BOX_RIGHT, 391.0), 3,
                         friction=0.1, elasticity=0.05, fill_color=CRATE)
        self.b0_hatch = b.static_segment((181.0, B0_HATCH_Y), (219.0, B0_HATCH_Y), 3,
                                         friction=0.2, elasticity=0.0, fill_color=MECH)

        # R0 pipe: horizontal run from the pool wall, then down into the
        # crate ceiling. Purely visual; the pool's right wall keeps every
        # physical ball out of this region.
        b.visual_segment((POOL_RIGHT, R0_PIPE_Y - 10), (378.0, R0_PIPE_Y - 10), 3,
                         fill_color=PIPE, stroke_color=PIPE)
        b.visual_segment((POOL_RIGHT, R0_PIPE_Y + 10), (378.0, R0_PIPE_Y + 10), 3,
                         fill_color=PIPE, stroke_color=PIPE)
        b.visual_segment((358.0, R0_PIPE_Y), (358.0, R0_PIPE_BOTTOM), 3,
                         fill_color=PIPE, stroke_color=PIPE)
        b.visual_segment((378.0, R0_PIPE_Y), (378.0, R0_PIPE_BOTTOM), 3,
                         fill_color=PIPE, stroke_color=PIPE)
        # R0 crate: ceiling with a pipe-width gap, conveyor floor, gate.
        b.static_segment((R0_BOX_LEFT, R0_CEIL_Y), (356.0, R0_CEIL_Y), 3,
                         friction=0.1, elasticity=0.05, fill_color=CRATE)
        b.static_segment((380.0, R0_CEIL_Y), (396.0, R0_CEIL_Y), 3,
                         friction=0.1, elasticity=0.05, fill_color=CRATE)
        b.static_segment((R0_BOX_LEFT, R0_CEIL_Y), (R0_BOX_LEFT, R0_FLOOR_Y), 3,
                         friction=0.1, elasticity=0.05, fill_color=CRATE)
        b.static_segment((R0_BOX_LEFT, R0_FLOOR_Y), (396.0, R0_FLOOR_Y), 3,
                         friction=0.5, elasticity=0.05,
                         surface_velocity=(EXIT_VX, 0.0), fill_color=CRATE)
        self.r0_gate = b.static_segment((R0_GATE_X, 296.0), (R0_GATE_X, 326.0), 3,
                                        friction=0.1, elasticity=0.05, fill_color=MECH)

        # Dynamic visuals, all hidden until used.
        def dash(path_start):
            return b.visual_segment(path_start, path_start, 3.5,
                                    fill_color=NO_DASH, stroke_color=NO_DASH,
                                    dynamic=True)

        self.boxes = {
            "b0": {
                "phase": "idle", "t": 0.0, "ball": None,
                "spawn": B0_SPAWN,
                "fill": b.visual_segment((B0_PIPE_X, B0_FILL_BOTTOM),
                                         (B0_PIPE_X, B0_FILL_BOTTOM),
                                         B0_FILL_RADIUS, fill_color=NO_WATER,
                                         stroke_color=NO_WATER, dynamic=True),
                "fill_bottom": B0_FILL_BOTTOM, "fill_height": B0_FILL_HEIGHT,
                "fill_x": B0_PIPE_X,
                "path": ((B0_PIPE_X, POOL_FLOOR + 4), (B0_PIPE_X, B0_PIPE_BOTTOM - 4)),
                "dashes": [dash((B0_PIPE_X, POOL_FLOOR + 4)) for _ in range(DASHES_PER_PIPE)],
                "tap": b.visual_segment((188.0, 338.0), (212.0, 338.0), 3,
                                        fill_color=NO_MECH, stroke_color=NO_MECH,
                                        dynamic=True),
                "hatch": self.b0_hatch,
            },
            "r0": {
                "phase": "idle", "t": 0.0, "ball": None,
                "spawn": R0_SPAWN,
                "fill": b.visual_segment((R0_FILL_X, R0_FILL_BOTTOM),
                                         (R0_FILL_X, R0_FILL_BOTTOM),
                                         R0_FILL_RADIUS, fill_color=NO_WATER,
                                         stroke_color=NO_WATER, dynamic=True),
                "fill_bottom": R0_FILL_BOTTOM, "fill_height": R0_FILL_HEIGHT,
                "fill_x": R0_FILL_X,
                "path": ((POOL_RIGHT + 4, R0_PIPE_Y), (R0_PIPE_X, R0_PIPE_Y),
                         (R0_PIPE_X, R0_PIPE_BOTTOM - 4)),
                "dashes": [dash((POOL_RIGHT + 4, R0_PIPE_Y)) for _ in range(DASHES_PER_PIPE)],
                "tap": b.visual_segment((358.0, 262.0), (378.0, 262.0), 3,
                                        fill_color=NO_MECH, stroke_color=NO_MECH,
                                        dynamic=True),
                "hatch": self.r0_gate,
            },
        }
        for box in self.boxes.values():
            length = 0.0
            path = box["path"]
            for a, end in zip(path, path[1:]):
                length += math.hypot(end[0] - a[0], end[1] - a[1])
            box["path_len"] = length

        self.splash_rays = [
            b.visual_segment((200.0, WATER_TOP), (200.0, WATER_TOP), 3,
                             fill_color=NO_SPLASH, stroke_color=NO_SPLASH,
                             dynamic=True)
            for _ in range(SPLASH_RAYS)
        ]

    def update(self, b: TileBuilder, dt: float) -> None:
        self._update_pool(dt)
        for box in self.boxes.values():
            self._update_box(box, dt)
        self._draw_splash(dt)
        box = self.boxes[self.next_box]
        if box["phase"] == "idle" and self.stockpile:
            box["ball"] = self.stockpile.pop(0)
            box["phase"] = "flow"
            box["t"] = 0.0
            self.next_box = "r0" if self.next_box == "b0" else "b0"

    def _update_pool(self, dt: float) -> None:
        for ball in self.restore_colors:
            try:
                ball.set_fill_color(BALL_FILL)
                ball.set_stroke_color(BALL_STROKE)
            except PermissionError:
                pass
        self.restore_colors.clear()
        drag = WATER_DRAG ** (dt * 120.0)
        for ball in tuple(self.sinking):
            try:
                _, y = ball.position
                vx, vy = ball.velocity
            except PermissionError:
                self.sinking.discard(ball)
                continue
            if ball.paused:
                self.sinking.discard(ball)
                continue
            ball.set_velocity((vx * drag, vy * drag))
            depth = (y - CAPTURE_TOP) / (CAPTURE_BOTTOM - CAPTURE_TOP)
            alpha = int(255 * max(0.0, min(1.0, 1.0 - depth)))
            ball.set_fill_color(BALL_FILL[:3] + (alpha,))
            ball.set_stroke_color(BALL_STROKE[:3] + (alpha,))
            if depth >= 1.0:
                ball.pause()
                self.sinking.discard(ball)
                self.stockpile.append(ball)

    def _update_box(self, box: dict, dt: float) -> None:
        phase = box["phase"]
        if phase == "flow":
            box["t"] += dt
            self._draw_dashes(box)
            level = min(1.0, box["t"] / FLOW_SECONDS)
            self._draw_fill(box, level, 210)
            if box["t"] >= FLOW_SECONDS:
                self._hide_dashes(box)
                box["tap"].set_fill_color(MECH)
                ball = box["ball"]
                try:
                    ball.set_position(box["spawn"])
                    ball.set_velocity((0.0, 0.0))
                    ball.set_fill_color(BALL_FILL[:3] + (0,))
                    ball.set_stroke_color(BALL_STROKE[:3] + (0,))
                    ball.resume()
                except (PermissionError, ValueError, RuntimeError):
                    box["ball"] = None
                    box["phase"] = "recover"
                    box["t"] = 0.0
                    return
                box["phase"] = "condense"
                box["t"] = 0.0
        elif phase == "condense":
            box["t"] += dt
            progress = min(1.0, box["t"] / CONDENSE_SECONDS)
            alpha = int(255 * progress)
            ball = box["ball"]
            if ball is not None:
                try:
                    ball.set_fill_color(BALL_FILL[:3] + (alpha,))
                    ball.set_stroke_color(BALL_STROKE[:3] + (alpha,))
                except PermissionError:
                    box["ball"] = None
            self._draw_fill(box, 1.0, int(210 * (1.0 - progress)))
            if box["t"] >= CONDENSE_SECONDS:
                self._draw_fill(box, 0.0, 0)
                box["hatch"].pause()
                if ball is not None and box["hatch"] is self.r0_gate:
                    try:
                        # Match the conveyor's surface speed so the exit
                        # reads as the floor carrying the ball out.
                        ball.set_velocity((EXIT_VX, 0.0))
                    except PermissionError:
                        box["ball"] = None
                box["phase"] = "release"
                box["t"] = 0.0
        elif phase == "release":
            box["t"] += dt
            done = box["t"] >= B0_RELEASE_SECONDS
            if box["hatch"] is self.r0_gate:
                ball = box["ball"]
                gone = True
                if ball is not None:
                    try:
                        gone = ball.position[0] > R0_GATE_CLEAR_X
                    except PermissionError:
                        gone = True
                done = gone or box["t"] >= R0_RELEASE_TIMEOUT
            if done:
                box["hatch"].resume()
                box["phase"] = "recover"
                box["t"] = 0.0
        elif phase == "recover":
            box["t"] += dt
            alpha = int(MECH[3] * max(0.0, 1.0 - box["t"] / RECOVER_SECONDS))
            box["tap"].set_fill_color(MECH[:3] + (alpha,))
            if box["t"] >= RECOVER_SECONDS:
                box["tap"].set_fill_color(NO_MECH)
                box["phase"] = "idle"
                box["ball"] = None

    def _draw_fill(self, box: dict, level: float, alpha: int) -> None:
        x = box["fill_x"]
        bottom = box["fill_bottom"]
        top = bottom - box["fill_height"] * level
        box["fill"].set_segment_points((x, bottom), (x, top))
        box["fill"].set_fill_color(WATER[:3] + (alpha,))

    def _draw_dashes(self, box: dict) -> None:
        length = box["path_len"]
        speed = length / FLOW_SECONDS
        for i, dash in enumerate(box["dashes"]):
            s = (box["t"] * speed + i * length / DASHES_PER_PIPE) % length
            cx, cy, dx, dy = _path_point(box["path"], s)
            dash.set_segment_points(
                _clamp((cx - 7 * dx, cy - 7 * dy)),
                _clamp((cx + 7 * dx, cy + 7 * dy)),
            )
            dash.set_fill_color(DASH)

    @staticmethod
    def _hide_dashes(box: dict) -> None:
        for dash in box["dashes"]:
            dash.set_fill_color(NO_DASH)

    def _draw_splash(self, dt: float) -> None:
        self.splash_t = max(0.0, self.splash_t - dt)
        if self.splash_t <= 0:
            for ray in self.splash_rays:
                ray.set_fill_color(NO_SPLASH)
            return
        progress = 1.0 - self.splash_t / SPLASH_SECONDS
        inner = 5 + 16 * progress
        outer = 12 + 26 * progress
        alpha = int(SPLASH[3] * (1.0 - progress))
        cx, cy = self.splash_center
        for i, ray in enumerate(self.splash_rays):
            theta = math.radians(-150 + i * 30)
            ux, uy = math.cos(theta), math.sin(theta)
            ray.set_segment_points(
                _clamp((cx + inner * ux, cy + inner * uy)),
                _clamp((cx + outer * ux, cy + outer * uy)),
            )
            ray.set_fill_color(SPLASH[:3] + (alpha,))


def _path_point(path, s: float):
    """Point and unit direction at distance s along a polyline."""
    for a, end in zip(path, path[1:]):
        segment = math.hypot(end[0] - a[0], end[1] - a[1])
        if segment > 0 and s <= segment:
            t = s / segment
            return (a[0] + (end[0] - a[0]) * t,
                    a[1] + (end[1] - a[1]) * t,
                    (end[0] - a[0]) / segment,
                    (end[1] - a[1]) / segment)
    a, end = path[-2], path[-1]
    segment = math.hypot(end[0] - a[0], end[1] - a[1]) or 1.0
    return end[0], end[1], (end[0] - a[0]) / segment, (end[1] - a[1]) / segment


def _clamp(point):
    return (
        min(396.0, max(4.0, point[0])),
        min(396.0, max(4.0, point[1])),
    )
