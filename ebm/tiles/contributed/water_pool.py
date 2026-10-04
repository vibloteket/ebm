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
# the pool to two fill boxes; each box is exactly one ball plus a one-unit
# margin. The boxes alternate strictly: the pipe runs while a stack of
# horizontal water segments fills the box from the bottom up, the tap
# closes, a stockpiled ball resumes behind the foreground water square,
# the water fades out leaving the ball, and a sliding hatch/gate (never a
# vanishing one) lets the ball out. No ball ever travels a pipe — the move
# happens while the ball is paused and invisible.
#
# Throughput: one box cycle is ~1.4 s, so the alternating pair sustains
# ~1.5 balls/s against the 0.8 balls/s nominal supply; the stockpile stays
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
RELEASE_TIMEOUT = 1.0
GATE_SPEED = 500.0
R0_GATE_CLEAR_X = 413.0
B0_HATCH_CLEAR_Y = 410.0
EXIT_VX = 340.0
DASHES_PER_PIPE = 3
FILL_SEGMENTS = 8

# B0: pipe drops from the pool floor into a ball-sized crate whose floor is
# a hatch that slides right to open.
B0_PIPE_X = 200.0
B0_BOX_LEFT = 181.0
B0_BOX_RIGHT = 219.0
B0_BOX_TOP = 351.0
B0_HATCH_Y = 388.0
B0_HATCH_SLIDE = 38.0
B0_SPAWN = (200.0, 370.0)

# R0: pipe leaves the pool wall, elbows down (left wall of the vertical run
# starts at the horizontal pipe's bottom, right wall at its top), and enters
# the box ceiling. A gate slides up to release; the conveyor floor plus an
# exit-speed kick carry the ball through the band.
R0_PIPE_Y = 183.0
R0_PIPE_LEFT = 358.0
R0_PIPE_RIGHT = 378.0
R0_BOX_LEFT = 356.0
R0_CEIL_Y = 293.0
R0_FLOOR_Y = 330.0
R0_GATE_X = 394.0
R0_GATE_Y = 311.0
R0_GATE_SLIDE = 33.0
R0_SPAWN = (375.0, 312.0)

SPLASH_SECONDS = 0.30
SPLASH_RAYS = 5

BALL_FILL = (22, 114, 212, 255)
BALL_STROKE = (12, 63, 143, 255)
WATER = (22, 114, 212, 190)
FILL = (22, 114, 212, 210)
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
    """Balls splash into a pool and dissolve; pipe water fills two
    ball-sized boxes that condense the water back into balls at B0 and R0,
    strictly alternating."""

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
        b.visual_segment((190.0, POOL_FLOOR - 2), (190.0, B0_BOX_TOP), 3,
                         fill_color=PIPE, stroke_color=PIPE)
        b.visual_segment((210.0, POOL_FLOOR - 2), (210.0, B0_BOX_TOP), 3,
                         fill_color=PIPE, stroke_color=PIPE)
        # B0 crate: ceiling with a pipe-width gap, sliding hatch floor.
        b.static_segment((B0_BOX_LEFT, B0_BOX_TOP), (B0_BOX_LEFT, 391.0), 3,
                         friction=0.1, elasticity=0.05, fill_color=CRATE)
        b.static_segment((B0_BOX_RIGHT, B0_BOX_TOP), (B0_BOX_RIGHT, 391.0), 3,
                         friction=0.1, elasticity=0.05, fill_color=CRATE)
        b.static_segment((B0_BOX_LEFT, B0_BOX_TOP), (190.0, B0_BOX_TOP), 3,
                         friction=0.1, elasticity=0.05, fill_color=CRATE)
        b.static_segment((210.0, B0_BOX_TOP), (B0_BOX_RIGHT, B0_BOX_TOP), 3,
                         friction=0.1, elasticity=0.05, fill_color=CRATE)
        b0_hatch = b.kinematic_body((200.0, B0_HATCH_Y))
        b.segment_shape(b0_hatch, (-19.0, 0.0), (19.0, 0.0), 3,
                        density=0.01, friction=0.2, elasticity=0.0,
                        fill_color=MECH)

        # R0 pipe: horizontal run from the pool wall, then an elbow down into
        # the box ceiling. The vertical run's left wall starts at the
        # horizontal pipe's bottom wall, its right wall at the top wall.
        b.visual_segment((POOL_RIGHT, R0_PIPE_Y - 10), (R0_PIPE_RIGHT, R0_PIPE_Y - 10), 3,
                         fill_color=PIPE, stroke_color=PIPE)
        b.visual_segment((POOL_RIGHT, R0_PIPE_Y + 10), (R0_PIPE_LEFT, R0_PIPE_Y + 10), 3,
                         fill_color=PIPE, stroke_color=PIPE)
        b.visual_segment((R0_PIPE_LEFT, R0_PIPE_Y + 10), (R0_PIPE_LEFT, R0_CEIL_Y), 3,
                         fill_color=PIPE, stroke_color=PIPE)
        b.visual_segment((R0_PIPE_RIGHT, R0_PIPE_Y - 10), (R0_PIPE_RIGHT, R0_CEIL_Y), 3,
                         fill_color=PIPE, stroke_color=PIPE)
        # R0 crate: ceiling between pipe and gate, conveyor floor, gate that
        # slides up through the ceiling to open.
        b.static_segment((R0_BOX_LEFT, R0_CEIL_Y), (R0_BOX_LEFT, R0_FLOOR_Y), 3,
                         friction=0.1, elasticity=0.05, fill_color=CRATE)
        b.static_segment((R0_PIPE_RIGHT, R0_CEIL_Y), (397.0, R0_CEIL_Y), 3,
                         friction=0.1, elasticity=0.05, fill_color=CRATE)
        b.static_segment((R0_BOX_LEFT, R0_FLOOR_Y), (397.0, R0_FLOOR_Y), 3,
                         friction=0.5, elasticity=0.05,
                         surface_velocity=(EXIT_VX, 0.0), fill_color=CRATE)
        r0_gate = b.kinematic_body((R0_GATE_X, R0_GATE_Y))
        b.segment_shape(r0_gate, (0.0, -15.0), (0.0, 15.0), 3,
                        density=0.01, friction=0.1, elasticity=0.05,
                        fill_color=MECH)

        # Dynamic visuals, all hidden until used.
        def dash(start):
            return b.visual_segment(start, start, 3.5,
                                    fill_color=NO_DASH, stroke_color=NO_DASH,
                                    dynamic=True)

        def fill_stack(x0, x1, y_bottom, y_top):
            step = (y_bottom - y_top) / (FILL_SEGMENTS - 1)
            return [
                b.visual_segment((x0, y_bottom - i * step), (x1, y_bottom - i * step), 2,
                                 fill_color=NO_WATER, stroke_color=NO_WATER,
                                 dynamic=True, foreground=True)
                for i in range(FILL_SEGMENTS)
            ]

        self.boxes = {
            "b0": {
                "phase": "idle", "t": 0.0, "ball": None,
                "spawn": B0_SPAWN, "kick": None,
                "fill_segs": fill_stack(186.0, 214.0, 383.0, 355.0),
                "path": ((B0_PIPE_X, POOL_FLOOR + 4), (B0_PIPE_X, B0_BOX_TOP - 7)),
                "dashes": [dash((B0_PIPE_X, POOL_FLOOR + 4)) for _ in range(DASHES_PER_PIPE)],
                "tap": b.visual_segment((190.0, 344.0), (210.0, 344.0), 2.5,
                                        fill_color=NO_MECH, stroke_color=NO_MECH,
                                        dynamic=True),
                "gate": b0_hatch,
                "gate_closed": (200.0, B0_HATCH_Y),
                "gate_open_pos": (200.0 + B0_HATCH_SLIDE, B0_HATCH_Y),
                "clear_axis": "y",
                "clear_at": B0_HATCH_CLEAR_Y,
            },
            "r0": {
                "phase": "idle", "t": 0.0, "ball": None,
                "spawn": R0_SPAWN, "kick": (EXIT_VX, 0.0),
                "fill_segs": fill_stack(361.0, 389.0, 325.0, 297.0),
                "path": ((POOL_RIGHT + 4, R0_PIPE_Y), (368.0, R0_PIPE_Y),
                         (368.0, R0_CEIL_Y - 5)),
                "dashes": [dash((POOL_RIGHT + 4, R0_PIPE_Y)) for _ in range(DASHES_PER_PIPE)],
                "tap": b.visual_segment((359.0, 288.0), (377.0, 288.0), 2.5,
                                        fill_color=NO_MECH, stroke_color=NO_MECH,
                                        dynamic=True),
                "gate": r0_gate,
                "gate_closed": (R0_GATE_X, R0_GATE_Y),
                "gate_open_pos": (R0_GATE_X, R0_GATE_Y - R0_GATE_SLIDE),
                "clear_axis": "x",
                "clear_at": R0_GATE_CLEAR_X,
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
            box["gate_open"] = False
            box["cleared"] = False
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
            self._draw_fill(box, min(1.0, box["t"] / FLOW_SECONDS), FILL[3])
            if box["t"] >= FLOW_SECONDS:
                self._hide_dashes(box)
                box["tap"].set_fill_color(MECH)
                ball = box["ball"]
                try:
                    ball.set_position(box["spawn"])
                    ball.set_velocity((0.0, 0.0))
                    # Fully colored from the start; the foreground water
                    # square hides it until the water fades out.
                    ball.set_fill_color(BALL_FILL)
                    ball.set_stroke_color(BALL_STROKE)
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
            self._draw_fill(box, 1.0, int(FILL[3] * (1.0 - progress)))
            if box["t"] >= CONDENSE_SECONDS:
                self._draw_fill(box, 0.0, 0)
                box["phase"] = "release"
                box["t"] = 0.0
        elif phase == "release":
            box["t"] += dt
            if not box["gate_open"]:
                if self._drive(box["gate"], box["gate_open_pos"], dt):
                    box["gate_open"] = True
                    ball = box["ball"]
                    if ball is not None and box["kick"] is not None:
                        try:
                            # Match the conveyor's surface speed so the exit
                            # reads as the floor carrying the ball out.
                            ball.set_velocity(box["kick"])
                        except PermissionError:
                            box["ball"] = None
            elif not box["cleared"]:
                ball = box["ball"]
                gone = ball is None
                if ball is not None:
                    try:
                        gone = ball.position[0 if box["clear_axis"] == "x" else 1] > box["clear_at"]
                    except PermissionError:
                        gone = True
                if gone or box["t"] >= RELEASE_TIMEOUT:
                    box["cleared"] = True
            elif self._drive(box["gate"], box["gate_closed"], dt):
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

    @staticmethod
    def _drive(gate, target, dt: float) -> bool:
        """Servo the gate toward its target without overshoot; True on arrival."""
        x, y = gate.position
        dx, dy = target[0] - x, target[1] - y
        if abs(dx) <= 0.5 and abs(dy) <= 0.5:
            gate.set_velocity((0.0, 0.0))
            if (x, y) != target:
                gate.set_position(target)
            return True
        step = max(dt, 1 / 240)
        distance = math.hypot(dx, dy)
        if distance <= GATE_SPEED * step:
            gate.set_velocity((dx / step, dy / step))  # Arrive exactly this frame.
        else:
            gate.set_velocity((GATE_SPEED * dx / distance, GATE_SPEED * dy / distance))
        return False

    def _draw_fill(self, box: dict, level: float, alpha: int) -> None:
        shown = int(level * FILL_SEGMENTS + 1e-9)
        for i, segment in enumerate(box["fill_segs"]):
            segment.set_fill_color(FILL[:3] + (alpha,) if i < shown else NO_WATER)

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
