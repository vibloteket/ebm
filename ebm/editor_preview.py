from __future__ import annotations

import math
import random

from js import window
from pyodide.ffi import create_proxy

from . import editor_runtime
from .ball_physics import configure_ball_body, limit_space_ball_speeds
from .editor_console import console_muted, console_phase
from .debug_demo import Ball, _draw_port_overlays
from .ports import BALL_RADIUS, COLUMN_OFFSET, MAX_EXIT_ANGLE_DEGREES, Port, PORT_SPECS, TILE_SIZE, entry_velocity, tile_origin
from .tile_api import BALL_COLLISION_TYPE, BALL_ELASTICITY, BALL_FRICTION, TileBuilder, TileResourceRegistry, VisualSegment, ball_shape_filter


_preview = None
_canvas = None
_last_ts = None
_paused = False
_view = "simulation"
_failure_replay = None
_replay_started = None
_proxies = []


class EditorPreview:
    def __init__(self, mode="single"):
        import pymunk
        self.space = pymunk.Space()
        self.space.gravity = (0, 1800)
        self.registry = TileResourceRegistry.for_space(self.space)
        self.balls = []
        self.rng = random.Random(17)
        self.spawn_clocks = {}
        self.owners = []
        self.configure(mode)

    def configure(self, mode):
        if editor_runtime._runtime.tile_class is None:
            raise RuntimeError("Run valid tile source first")
        for ball in list(self.balls):
            self.remove_ball(ball)
        for owner, _, _ in self.owners:
            self.registry.destroy_owner(owner)
        self.owners = []
        self.tile_class = editor_runtime._runtime.tile_class
        self.mode = "repeat" if str(mode) == "repeat" else "single"
        size = 3 if self.mode == "repeat" else 1
        owner = 1
        for row in range(size):
            for col in range(size):
                is_log_tile = (row == size // 2 and col == size // 2)
                output_context = console_phase(f"build {row},{col}") if is_log_tile else console_muted()
                with output_context:
                    tile = self.tile_class()
                    builder = TileBuilder(self.registry, owner, tile_origin(row, col))
                    tile.build(builder)
                self.owners.append((owner, tile, builder))
                owner += 1
        # Every open boundary input has an independent phase and cadence.
        # Real neighboring mechanisms do not deliver all balls in lockstep.
        self.spawn_clocks = {
            boundary: self.rng.uniform(0.05, 0.85)
            for boundary in self._boundary_inputs()
        }

    @property
    def grid_size(self):
        return 3 if self.mode == "repeat" else 1

    def step(self, dt):
        for boundary in list(self.spawn_clocks):
            self.spawn_clocks[boundary] -= dt
            if self.spawn_clocks[boundary] <= 0:
                port, ox, oy = boundary
                self.spawn(port, ox, oy)
                # Vary the interval as well as the initial phase. This exposes
                # mechanisms that only work when inputs arrive simultaneously.
                self.spawn_clocks[boundary] += self.rng.uniform(0.65, 1.35)
        for _ in range(max(1, int(dt / (1 / 60)))):
            for owner, tile, builder in self.owners:
                row, col = divmod(owner - 1, self.grid_size)
                is_log_tile = (row == self.grid_size // 2 and col == self.grid_size // 2)
                output_context = console_phase(f"update {row},{col}") if is_log_tile else console_muted()
                with output_context:
                    tile.update(builder, 1 / 60)
            self.space.step(1 / 60)
            self.registry.advance(1 / 60)
            limit_space_ball_speeds(self.balls)
        edge_x = self.grid_size * TILE_SIZE
        edge_y = self.grid_size * TILE_SIZE + COLUMN_OFFSET
        for ball in list(self.balls):
            x, y = ball.body.position
            if x < -200 or x > edge_x + 200 or y < -200 or y > edge_y + 300:
                self.remove_ball(ball)

    def _boundary_inputs(self):
        size = self.grid_size
        inputs = [(Port.T0, *tile_origin(0, col)) for col in range(size)]
        for row in range(size):
            inputs.append((Port.L0, *tile_origin(row, 0)))
        return inputs

    def spawn_boundary(self):
        """Manual canvas click emits one ball at every boundary input."""
        for port, ox, oy in self._boundary_inputs():
            self.spawn(port, ox, oy)

    def spawn(self, port, ox, oy):
        import pymunk
        spec = PORT_SPECS[port]
        dx = self.rng.uniform(-spec.x_range, spec.x_range)
        dy = self.rng.uniform(-spec.y_range, spec.y_range)
        speed = self.rng.uniform(1, 600)
        angle = self.rng.uniform(-MAX_EXIT_ANGLE_DEGREES, MAX_EXIT_ANGLE_DEGREES)
        vx, vy = entry_velocity(port, speed, angle)
        if port == Port.T0:
            pos = (ox + spec.x_center + dx, oy + BALL_RADIUS + 0.5 + dy)
        elif port == Port.L0:
            pos = (ox + BALL_RADIUS + 0.5 + dx, oy + spec.y_center + dy)
        body = pymunk.Body(1, pymunk.moment_for_circle(1, 0, BALL_RADIUS))
        configure_ball_body(body)
        body.position = pos
        body.velocity = (vx, vy)
        shape = pymunk.Circle(body, BALL_RADIUS)
        shape.friction = BALL_FRICTION; shape.elasticity = BALL_ELASTICITY
        shape.ebm_fill_color = (22, 114, 212, 255); shape.ebm_stroke_color = (12, 63, 143, 255)
        shape.collision_type = BALL_COLLISION_TYPE; shape.filter = ball_shape_filter()
        self.space.add(body, shape)
        self.balls.append(Ball(body, shape))

    def remove_ball(self, ball):
        try: self.space.remove(ball.shape, ball.body)
        except Exception: pass
        try: self.balls.remove(ball)
        except ValueError: pass


def start(canvas):
    global _preview, _canvas, _last_ts
    _canvas = canvas
    _preview = EditorPreview()
    _last_ts = None

    def resize(_event=None):
        canvas.width = max(300, int(canvas.clientWidth))
        canvas.height = max(260, int(canvas.clientHeight))

    def click(_event=None):
        if _preview and _view == "simulation": _preview.spawn_boundary()

    resize_proxy = create_proxy(resize); click_proxy = create_proxy(click)
    _proxies.extend((resize_proxy, click_proxy))
    window.addEventListener("resize", resize_proxy)
    canvas.addEventListener("click", click_proxy)
    resize()

    def frame(ts):
        global _last_ts
        # Pausing freezes live simulation, but validation replays must keep
        # drawing even if the user paused before entering validation mode.
        if not _paused or _view == "validation":
            dt = 1/60 if _last_ts is None else max(0, min(.05, (ts-_last_ts)/1000))
            _last_ts = ts
            if _preview:
                if _view == "simulation": _preview.step(dt)
                draw(canvas, _preview)
        window.requestAnimationFrame(frame_proxy)

    frame_proxy = create_proxy(frame); _proxies.append(frame_proxy)
    window.requestAnimationFrame(frame_proxy)


def refresh(mode="single"):
    global _preview
    if _preview is None:
        return
    # Rebuild even while paused, then draw the fresh state once without
    # advancing physics. This keeps Run useful as an edit/inspect workflow.
    _preview.configure(str(mode))
    if _canvas is not None:
        draw(_canvas, _preview)


def set_paused(paused):
    """Pause physics and drawing while keeping the animation callback lightweight."""
    global _paused, _last_ts
    _paused = bool(paused)
    _last_ts = None
    return _paused


def set_view(view):
    """Switch between live simulation and a stationary validation replay stage."""
    global _view, _failure_replay, _replay_started, _last_ts
    value = str(view)
    _view = "validation" if value == "validation" else "simulation"
    _last_ts = None
    _failure_replay = None
    _replay_started = None
    if _view == "validation" and _preview is not None:
        for ball in list(_preview.balls):
            _preview.remove_ball(ball)
    return _view


def replay_failure(detail_json):
    """Overlay one validator trajectory without replacing the live preview."""
    global _failure_replay, _replay_started
    import json
    detail = json.loads(str(detail_json))
    trajectory = detail.get("trajectory") or []
    if not trajectory:
        return False
    _failure_replay = detail
    _replay_started = float(window.performance.now())
    if _canvas is not None and _preview is not None:
        draw(_canvas, _preview)
    return True


def _replay_position(now):
    global _replay_started
    if not _failure_replay or not _failure_replay.get("trajectory"):
        return None
    points = _failure_replay["trajectory"]
    duration = max(0.05, float(points[-1][0]))
    elapsed = ((now - (_replay_started or now)) / 1000) % (duration + 0.7)
    if elapsed > duration:
        return points[-1][1], points[-1][2], True
    previous = points[0]
    for point in points[1:]:
        if elapsed <= point[0]:
            span = max(1e-6, point[0] - previous[0])
            mix = (elapsed - previous[0]) / span
            return previous[1] + (point[1] - previous[1]) * mix, previous[2] + (point[2] - previous[2]) * mix, False
        previous = point
    return points[-1][1], points[-1][2], True


def _canvas_color(color):
    r,g,b,a=color
    return f"rgba({r},{g},{b},{a/255:.4f})"


def _draw_sensor_overlay(ctx, shape, sx, sy, scale):
    """Draw editor-only sensor geometry without changing production rendering."""
    if type(shape).__name__ != "Poly":
        return
    points = [shape.body.local_to_world(vertex) for vertex in shape.get_vertices()]
    if not points:
        return
    ctx.save()
    ctx.beginPath(); ctx.moveTo(sx(points[0].x), sy(points[0].y))
    for point in points[1:]:
        ctx.lineTo(sx(point.x), sy(point.y))
    ctx.closePath()
    ctx.fillStyle = "rgba(71,85,105,.13)"; ctx.fill()
    ctx.strokeStyle = "rgba(71,85,105,.62)"; ctx.lineWidth = max(1, 1.5 * scale)
    ctx.setLineDash([max(3, 8 * scale), max(2, 5 * scale)]); ctx.stroke()
    ctx.restore()


def draw(canvas, preview):
    ctx = canvas.getContext("2d")
    width, height = canvas.width, canvas.height
    ctx.fillStyle = "#f4e8c8"; ctx.fillRect(0, 0, width, height)
    world_width = preview.grid_size * TILE_SIZE
    world_height = preview.grid_size * TILE_SIZE + (COLUMN_OFFSET if preview.grid_size > 1 else 0)
    # Always fit the complete grid inside the canvas. A 3 × 3 grid needs a
    # scale below .3 on narrow mobile previews; clamping it to .3 clipped the
    # first and last rows instead of preserving the intended margins.
    scale = max(.01, min((width-36)/world_width, (height-44)/world_height))
    ox, oy = (width-world_width*scale)/2, (height-world_height*scale)/2
    sx=lambda x:ox+x*scale; sy=lambda y:oy+y*scale
    for _, _, builder in preview.owners:
        bx, by = builder.origin
        ctx.fillStyle="rgba(255,255,255,.2)";ctx.fillRect(sx(bx),sy(by),TILE_SIZE*scale,TILE_SIZE*scale)
        ctx.strokeStyle="rgba(91,78,52,.35)";ctx.lineWidth=1;ctx.strokeRect(sx(bx),sy(by),TILE_SIZE*scale,TILE_SIZE*scale)
        ctx.strokeStyle="#315aa8";ctx.lineCap="round"
        if preview.mode == "single":
            for shape in builder.visual_objects:
                if getattr(shape, "ebm_hidden", False):
                    _draw_sensor_overlay(ctx, shape, sx, sy, scale)
        for shape, style in builder.visual_items:
            fill=_canvas_color(style.fill_color);stroke=_canvas_color(style.stroke_color)
            if isinstance(shape,VisualSegment):
                if style.stroke_color[3]:ctx.beginPath();ctx.moveTo(sx(bx+shape.a[0]),sy(by+shape.a[1]));ctx.lineTo(sx(bx+shape.b[0]),sy(by+shape.b[1]));ctx.strokeStyle=stroke;ctx.lineWidth=max(2,(shape.radius*2+2)*scale);ctx.stroke()
                ctx.beginPath();ctx.moveTo(sx(bx+shape.a[0]),sy(by+shape.a[1]));ctx.lineTo(sx(bx+shape.b[0]),sy(by+shape.b[1]));ctx.strokeStyle=fill;ctx.lineWidth=max(2,shape.radius*2*scale);ctx.stroke()
            elif getattr(shape,"ebm_hidden",False):
                continue
            elif type(shape).__name__ == "Segment":
                a,b=shape.body.local_to_world(shape.a),shape.body.local_to_world(shape.b)
                if style.stroke_color[3]:ctx.beginPath();ctx.moveTo(sx(a.x),sy(a.y));ctx.lineTo(sx(b.x),sy(b.y));ctx.strokeStyle=stroke;ctx.lineWidth=max(2,(shape.radius*2+2)*scale);ctx.stroke()
                ctx.beginPath();ctx.moveTo(sx(a.x),sy(a.y));ctx.lineTo(sx(b.x),sy(b.y));ctx.strokeStyle=fill;ctx.lineWidth=max(2,shape.radius*2*scale);ctx.stroke()
            elif type(shape).__name__ == "Circle":
                p=shape.body.local_to_world(shape.offset)
                ctx.beginPath();ctx.arc(sx(p.x),sy(p.y),shape.radius*scale,0,math.tau);ctx.fillStyle=fill;ctx.fill();ctx.strokeStyle=stroke;ctx.lineWidth=2;ctx.stroke()
            elif type(shape).__name__ == "Poly":
                points=[shape.body.local_to_world(vertex) for vertex in shape.get_vertices()]
                if points:
                    ctx.beginPath();ctx.moveTo(sx(points[0].x),sy(points[0].y))
                    for point in points[1:]:ctx.lineTo(sx(point.x),sy(point.y))
                    ctx.closePath();ctx.fillStyle=fill;ctx.fill();ctx.strokeStyle=stroke;ctx.lineWidth=2;ctx.stroke()
    if preview.mode == "single":
        _draw_port_overlays(ctx, sx, sy, scale)
    for ball in preview.balls:
        if preview.registry.ball_is_paused(ball.body): continue
        p=ball.body.position;ctx.beginPath();ctx.arc(sx(p.x),sy(p.y),BALL_RADIUS*scale,0,math.tau)
        ctx.fillStyle=_canvas_color(getattr(ball.shape,"ebm_fill_color",(22,114,212,255)));ctx.fill()
        ctx.strokeStyle=_canvas_color(getattr(ball.shape,"ebm_stroke_color",(12,63,143,255)));ctx.lineWidth=1.5;ctx.stroke()
    replay = _replay_position(float(window.performance.now())) if _view == "validation" else None
    if replay is not None and preview.mode == "single":
        x, y, finished = replay
        points = _failure_replay["trajectory"]
        ctx.beginPath();ctx.moveTo(sx(points[0][1]),sy(points[0][2]))
        for point in points[1:]:ctx.lineTo(sx(point[1]),sy(point[2]))
        ctx.strokeStyle="rgba(190,24,24,.48)";ctx.lineWidth=max(2,2*scale);ctx.stroke()
        ctx.beginPath();ctx.arc(sx(x),sy(y),9*scale,0,math.tau)
        ctx.fillStyle="#dc2626";ctx.fill();ctx.strokeStyle="#7f1d1d";ctx.lineWidth=2;ctx.stroke()
        ctx.fillStyle="#7f1d1d";ctx.font="bold 12px system-ui"
        ctx.fillText(f"Replay: ball #{_failure_replay['id']} · {_failure_replay['entry']} → {_failure_replay['exit']}",12,18)
    ctx.fillStyle="rgba(54,45,35,.78)";ctx.font="12px system-ui"
    footer = f"{len(preview.balls)} balls · click to emit" if _view == "simulation" else ("Choose a failed run below to replay" if replay is None else "Validation replay · red path loops automatically")
    ctx.fillText(footer,12,height-12)
