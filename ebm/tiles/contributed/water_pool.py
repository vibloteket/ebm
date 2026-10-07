from __future__ import annotations

import math

from ebm import TileBase, TileBuilder, Vec2d

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
# square water layers fills the box from the bottom up, a stockpiled ball
# resumes behind the foreground water square, the water fades out leaving
# the ball, and a sliding hatch/gate (never a vanishing one) lets the ball
# out. No ball ever travels a pipe — the move happens while the ball is
# paused and invisible.
#
# Throughput: one box cycle is ~1.3 s, so the alternating pair sustains
# ~1.6 balls/s against the 0.8 balls/s nominal supply; the stockpile stays
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
RELEASE_TIMEOUT = 1.0
GATE_SPEED = 500.0
R0_GATE_CLEAR_X = 413.0
B0_HATCH_CLEAR_Y = 410.0
EXIT_VX = 340.0
DASHES_PER_PIPE = 3
PIPE_HALF = 7.0         # Pipe wall offset from centerline; interior fits the dashes.
PIPE_CAP_HEIGHT = 12
FILL_LAYERS = 12
FILL_ALPHA = 210

# B0: pipe drops from the pool floor into a ball-sized crate whose floor is
# a hatch that slides right to open. The pipe top starts below the floor's
# top face so its rounded cap never pokes into the pool.
B0_PIPE_X = 200.0
B0_PIPE_TOP = POOL_FLOOR + 8.0
B0_BOX_LEFT = 181.0
B0_BOX_RIGHT = 219.0
B0_BOX_TOP = 351.0
B0_HATCH_Y = 388.0
B0_HATCH_SLIDE = 38.0
B0_SPAWN = (200.0, 370.0)

# R0: pipe leaves the pool wall, elbows down (the vertical run's left wall
# starts at the horizontal pipe's bottom wall, its right wall at its top
# wall), and enters the box ceiling centered over the box. A gate slides up
# through the ceiling to release; the conveyor floor plus an exit-speed kick
# carry the ball through the band.
R0_PIPE_Y = 183.0
R0_PIPE_X = 375.0
R0_BOX_LEFT = 356.0
R0_CEIL_Y = 293.0
R0_FLOOR_Y = 330.0
R0_GATE_X = 394.0
R0_GATE_Y = 311.0
R0_GATE_SLIDE = 36.0
R0_SPAWN = (375.0, 312.0)

SPLASH_SECONDS = 0.30
SPLASH_RAYS = 5

BALL_FILL = (22, 114, 212, 255)
BALL_STROKE = (12, 63, 143, 255)
WATER = (22, 114, 212, 190)
FILL = (22, 114, 212, FILL_ALPHA)
NO_WATER = (22, 114, 212, 0)
SURFACE = (130, 190, 255, 230)
BASIN = (49, 90, 168, 255)
TUBE = (104, 110, 118, 255)
CRATE = (126, 131, 138, 255)
MECH = (220, 140, 35, 255)
DASH = (185, 220, 255, 245)
NO_DASH = (185, 220, 255, 0)
GLINT = (225, 242, 255, 220)
NO_GLINT = (225, 242, 255, 0)
GLINT_LAG = 0.09
SPLASH = (170, 210, 255, 230)
NO_SPLASH = (170, 210, 255, 0)


class WaterPool(TileBase):
    """Balls splash into a pool and dissolve; pipe water fills two
    ball-sized boxes that condense the water back into balls at B0 and R0,
    strictly alternating."""

    author = "Victor"
    enabled = True  # Editor-only until the user asks to enable.

    def build(self, b: TileBuilder) -> None:
        self.stockpile = []
        self.sinking = set()
        self.restore_colors = []
        self.next_box = "b0"
        self.splash_t = 0.0
        self.splash_center = Vec2d(200.0, WATER_TOP)

        # The basin. The left rim sits below the L0 band with a slope so
        # even near-stationary entries roll in; the right wall runs to
        # RIM_TOP so even a 600 u/s L0 ball cannot fly over the pool (it
        # crosses the wall plane around y~190 and falls back in).
        b.static_segment((4.0, WATER_TOP), (4.0, POOL_FLOOR), 4,
                         friction=0.2, elasticity=0.05, fill_color=BASIN)
        b.static_segment((4.0, WATER_TOP), (28.0, 170.0), 4,
                         friction=0.2, elasticity=0.05, fill_color=BASIN)
        b.static_segment((POOL_RIGHT, RIM_TOP), (POOL_RIGHT, POOL_FLOOR), 4,
                         friction=0.2, elasticity=0.05, fill_color=BASIN)
        b.static_segment((4.0, POOL_FLOOR), (POOL_RIGHT, POOL_FLOOR), 4,
                         friction=0.3, elasticity=0.05, fill_color=BASIN)

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
                self.splash_center = Vec2d(min(max(x, 40.0), 296.0), WATER_TOP)

        def leave(event):
            ball = event.ball
            if ball in self.sinking:
                self.sinking.discard(ball)
                # Bounced out mid-fade: restore full color so no ghost ball
                # is left rolling around. Deferred: style writes inside
                # contact callbacks are unsafe.
                self.restore_colors.append(ball)

        b.on_ball_contact(sensor, begin=enter, separate=leave)

        def pipe_cap(x:float, y:float, horizontal:bool):
            """Make a pipe cap at x,y"""
            h = 10 if horizontal else 0
            v = 10 if not horizontal else 0
            left = x - PIPE_HALF - h
            top = y - PIPE_HALF - v
            right = x + PIPE_HALF + h
            bottom = y + PIPE_HALF + v
            b.visual_box(left,top, right, bottom,fill_color=TUBE, foreground=True)
        
        # B0 pipe: two vertical walls from just under the pool floor to the
        # crate top.
        b.visual_segment((B0_PIPE_X - PIPE_HALF, B0_PIPE_TOP), (B0_PIPE_X - PIPE_HALF, B0_BOX_TOP-2), 3,
                         fill_color=TUBE, stroke_color=TUBE)
        b.visual_segment((B0_PIPE_X + PIPE_HALF, B0_PIPE_TOP), (B0_PIPE_X + PIPE_HALF, B0_BOX_TOP-2), 3,
                         fill_color=TUBE, stroke_color=TUBE)


            
        pipe_cap(B0_PIPE_X, B0_PIPE_TOP+3, True)
        pipe_cap(B0_PIPE_X, B0_BOX_TOP-10, True)
        
        # B0 crate: ceiling with a pipe-width gap, sliding hatch floor.
        b.static_segment((B0_BOX_LEFT, B0_BOX_TOP), (B0_BOX_LEFT, 391.0), 3,
                         friction=0.1, elasticity=0.05, fill_color=CRATE)
        b.static_segment((B0_BOX_RIGHT, B0_BOX_TOP), (B0_BOX_RIGHT, 391.0), 3,
                         friction=0.1, elasticity=0.05, fill_color=CRATE)
        b.static_segment((B0_BOX_LEFT, B0_BOX_TOP), (B0_PIPE_X - PIPE_HALF, B0_BOX_TOP), 3,
                         friction=0.1, elasticity=0.05, fill_color=CRATE)
        b.static_segment((B0_PIPE_X + PIPE_HALF, B0_BOX_TOP), (B0_BOX_RIGHT, B0_BOX_TOP), 3,
                         friction=0.1, elasticity=0.05, fill_color=CRATE)
        b0_hatch = b.kinematic_body((200.0, B0_HATCH_Y))
        b.segment_shape(b0_hatch, (-19.0, 0.0), (19.0, 0.0), 3,
                        density=0.01, friction=0.2, elasticity=0.0,
                        fill_color=MECH)

        # R0 pipe: horizontal run from the pool wall, then an elbow down into
        # the box ceiling. The vertical run's left wall starts at the
        # horizontal pipe's bottom wall, its right wall at its top wall.
        b.visual_segment((POOL_RIGHT+7, R0_PIPE_Y - PIPE_HALF), (R0_PIPE_X + PIPE_HALF, R0_PIPE_Y - PIPE_HALF), 3,
                         fill_color=TUBE, stroke_color=TUBE)
        b.visual_segment((POOL_RIGHT+7, R0_PIPE_Y + PIPE_HALF), (R0_PIPE_X - PIPE_HALF, R0_PIPE_Y + PIPE_HALF), 3,
                         fill_color=TUBE, stroke_color=TUBE)
        b.visual_segment((R0_PIPE_X - PIPE_HALF, R0_PIPE_Y + PIPE_HALF), (R0_PIPE_X - PIPE_HALF, R0_CEIL_Y), 3,
                         fill_color=TUBE, stroke_color=TUBE)
        b.visual_segment((R0_PIPE_X + PIPE_HALF, R0_PIPE_Y - PIPE_HALF), (R0_PIPE_X + PIPE_HALF, R0_CEIL_Y), 3,
                         fill_color=TUBE, stroke_color=TUBE)

        pipe_cap(POOL_RIGHT+10, R0_PIPE_Y, False)
        pipe_cap(R0_PIPE_X, R0_CEIL_Y-10, True)
        
        # R0 crate: ceiling segments on both sides of the pipe (same style as
        # the B0 ceiling), conveyor floor, gate that slides up to open.
        b.static_segment((R0_BOX_LEFT, R0_CEIL_Y), (R0_BOX_LEFT, R0_FLOOR_Y), 3,
                         friction=0.1, elasticity=0.05, fill_color=CRATE)
        b.static_segment((R0_BOX_LEFT, R0_CEIL_Y), (R0_PIPE_X - PIPE_HALF, R0_CEIL_Y), 3,
                         friction=0.1, elasticity=0.05, fill_color=CRATE)
        b.static_segment((R0_PIPE_X + PIPE_HALF, R0_CEIL_Y), (397.0, R0_CEIL_Y), 3,
                         friction=0.1, elasticity=0.05, fill_color=CRATE)
        b.static_segment((R0_BOX_LEFT, R0_FLOOR_Y), (397.0, R0_FLOOR_Y), 3,
                         friction=0.5, elasticity=0.05,
                         surface_velocity=(EXIT_VX, 0.0), fill_color=CRATE)
        r0_gate = b.kinematic_body((R0_GATE_X, R0_GATE_Y))
        b.segment_shape(r0_gate, (0.0, -15.0), (0.0, 15.0), 3,
                        density=0.01, friction=0.1, elasticity=0.05,
                        fill_color=MECH)

        # Dynamic visuals, all hidden until used. Each pipe has two dash
        # layers: the main stream and a lighter glint slightly ahead in time.
        def dash(start, radius, color):
            return b.visual_segment(start, start, radius,
                                    fill_color=color, stroke_color=color,
                                    dynamic=True)

        def fill_stack(x0, x1, y_bottom, y_top):
            step = (y_bottom - y_top) / FILL_LAYERS
            return [
                b.visual_box(x0, y_bottom - (i + 1) * step, x1, y_bottom - i * step,
                             fill_color=NO_WATER, stroke_color=NO_WATER,
                             foreground=True)
                for i in range(FILL_LAYERS)
            ]

        self.boxes = {
            "b0": {
                "phase": "idle", "t": 0.0, "ball": None,
                "spawn": B0_SPAWN, "kick": None,
                "fill_segs": fill_stack(184.0, 216.0, 385.0, 355.0),
                "path": (Vec2d(B0_PIPE_X, POOL_FLOOR + 20), Vec2d(B0_PIPE_X, B0_BOX_TOP - 7)),
                "dashes": [dash((B0_PIPE_X, POOL_FLOOR + 4), 3.5, NO_DASH) for _ in range(DASHES_PER_PIPE)],
                "glints": [dash((B0_PIPE_X, POOL_FLOOR + 4), 2.0, NO_GLINT) for _ in range(DASHES_PER_PIPE)],
                "gate": b0_hatch,
                "gate_closed": (200.0, B0_HATCH_Y),
                "gate_open_pos": (200.0 + B0_HATCH_SLIDE, B0_HATCH_Y),
                "clear_axis": "y",
                "clear_at": B0_HATCH_CLEAR_Y,
            },
            "r0": {
                "phase": "idle", "t": 0.0, "ball": None,
                "spawn": R0_SPAWN, "kick": (EXIT_VX, 0.0),
                "fill_segs": fill_stack(360.0, 390.0, 327.0, 297.0),
                "path": (Vec2d(POOL_RIGHT + 20, R0_PIPE_Y), Vec2d(R0_PIPE_X, R0_PIPE_Y),
                         Vec2d(R0_PIPE_X, R0_CEIL_Y - 5)),
                "dashes": [dash((POOL_RIGHT + 4, R0_PIPE_Y), 3.5, NO_DASH) for _ in range(DASHES_PER_PIPE)],
                "glints": [dash((POOL_RIGHT + 4, R0_PIPE_Y), 2.0, NO_GLINT) for _ in range(DASHES_PER_PIPE)],
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
                length += (end - a).length
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
                velocity = ball.velocity
            except PermissionError:
                self.sinking.discard(ball)
                continue
            if ball.paused:
                self.sinking.discard(ball)
                continue
            ball.set_velocity(velocity * drag)
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
            self._draw_fill(box, min(1.0, box["t"] / FLOW_SECONDS), FILL_ALPHA)
            if box["t"] >= FLOW_SECONDS:
                self._hide_dashes(box)
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
                    box["phase"] = "idle"
                    return
                box["phase"] = "condense"
                box["t"] = 0.0
        elif phase == "condense":
            box["t"] += dt
            progress = min(1.0, box["t"] / CONDENSE_SECONDS)
            self._draw_fill(box, 1.0, int(FILL_ALPHA * (1.0 - progress)))
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
                box["phase"] = "idle"
                box["ball"] = None

    @staticmethod
    def _drive(gate, target, dt: float) -> bool:
        """Servo the gate toward its target without overshoot; True on arrival."""
        delta = Vec2d(*target) - gate.position
        if abs(delta.x) <= 0.5 and abs(delta.y) <= 0.5:
            gate.set_velocity((0.0, 0.0))
            if gate.position != target:
                gate.set_position(target)
            return True
        step = max(dt, 1 / 240)
        if delta.length <= GATE_SPEED * step:
            gate.set_velocity(delta / step)  # Arrive exactly this frame.
        else:
            gate.set_velocity(delta.normalized() * GATE_SPEED)
        return False

    @staticmethod
    def _draw_fill(box: dict, level: float, alpha: int) -> None:
        shown = math.ceil(level * FILL_LAYERS - 1e-9)
        for i, layer in enumerate(box["fill_segs"]):
            layer.set_fill_color(FILL[:3] + (alpha,) if i < shown else NO_WATER)

    def _draw_dashes(self, box: dict) -> None:
        length = box["path_len"]
        speed = length / FLOW_SECONDS
        for i, dash in enumerate(box["dashes"]):
            s = (box["t"] * speed + i * length / DASHES_PER_PIPE) % length
            _place_dash(box["path"], dash, s, DASH)
        for i, glint in enumerate(box["glints"]):
            s = ((box["t"] + GLINT_LAG) * speed + i * length / DASHES_PER_PIPE) % length
            _place_dash(box["path"], glint, s, GLINT)

    @staticmethod
    def _hide_dashes(box: dict) -> None:
        for dash in box["dashes"]:
            dash.set_fill_color(NO_DASH)
        for glint in box["glints"]:
            glint.set_fill_color(NO_GLINT)

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
        center = self.splash_center
        for i, ray in enumerate(self.splash_rays):
            direction = Vec2d(1, 0).rotated(math.radians(-150 + i * 30))
            ray.set_segment_points(
                _clamp(center + direction * inner),
                _clamp(center + direction * outer),
            )
            ray.set_fill_color(SPLASH[:3] + (alpha,))


def _place_dash(path, dash, s: float, color) -> None:
    center, direction = _path_point(path, s)
    offset = direction * 7
    dash.set_segment_points(_clamp(center - offset), _clamp(center + offset))
    dash.set_fill_color(color)


def _path_point(path, s: float):
    """Point and unit direction at distance s along a polyline."""
    for a, end in zip(path, path[1:]):
        segment = end - a
        if segment.length > 0 and s <= segment.length:
            direction = segment / segment.length
            return a + direction * s, direction
    segment = path[-1] - path[-2]
    direction = segment / (segment.length or 1.0)
    return path[-1], direction


def _clamp(point):
    return (
        min(396.0, max(4.0, point[0])),
        min(396.0, max(4.0, point[1])),
    )
