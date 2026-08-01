from __future__ import annotations

import math
import random

from js import window
from pyodide.ffi import create_proxy

from . import editor_runtime
from .editor_console import console_phase
from .debug_demo import Ball, _draw_port_overlays
from .ports import Port, PORT_SPECS, TILE_SIZE
from .tile_api import BALL_COLLISION_TYPE, TileBuilder, TileResourceRegistry, VisualSegment, ball_shape_filter
from .validator import _entry_base_velocity


_preview = None
_last_ts = None
_paused = False
_proxies = []


class EditorPreview:
    def __init__(self, route_index=0, mode="single"):
        import pymunk
        self.space = pymunk.Space()
        self.space.gravity = (0, 900)
        self.registry = TileResourceRegistry.for_space(self.space)
        self.balls = []
        self.rng = random.Random(17)
        self.spawn_clocks = {}
        self.owners = []
        self.configure(route_index, mode)

    def configure(self, route_index, mode):
        if editor_runtime._runtime.tile_class is None:
            raise RuntimeError("Run valid tile source first")
        for ball in list(self.balls):
            self.remove_ball(ball)
        for owner, _, _ in self.owners:
            self.registry.destroy_owner(owner)
        self.owners = []
        self.tile_class = editor_runtime._runtime.tile_class
        self.route_index = max(0, min(int(route_index), len(self.tile_class.routes) - 1))
        self.route = self.tile_class.routes[self.route_index]
        self.mode = "repeat" if str(mode) == "repeat" else "single"
        size = 3 if self.mode == "repeat" else 1
        owner = 1
        for row in range(size):
            for col in range(size):
                tile = self.tile_class(self.route)
                builder = TileBuilder(self.registry, owner, (col * TILE_SIZE, row * TILE_SIZE))
                with console_phase(f"build {row},{col}"):
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
                with console_phase(f"update {row},{col}"):
                    tile.update(builder, 1 / 60)
            self.space.step(1 / 60)
        edge = self.grid_size * TILE_SIZE
        for ball in list(self.balls):
            x, y = ball.body.position
            if x < -100 or x > edge + 100 or y < -100 or y > edge + 150:
                self.remove_ball(ball)

    def _boundary_inputs(self):
        size = self.grid_size
        inputs = [(Port.T0, col * TILE_SIZE, 0) for col in range(size)]
        for row in range(size):
            inputs.append((Port.L0, 0, row * TILE_SIZE))
            inputs.append((Port.R0, (size - 1) * TILE_SIZE, row * TILE_SIZE))
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
        dvx = self.rng.uniform(-spec.entry_vx_range, spec.entry_vx_range)
        dvy = self.rng.uniform(-spec.entry_vy_range, spec.entry_vy_range)
        vx, vy = _entry_base_velocity(port)
        if port == Port.T0:
            pos = (ox + spec.x_center + dx, oy + 8.5 + dy)
        elif port == Port.L0:
            pos = (ox + 8.5 + dx, oy + spec.y_center + dy)
        else:
            pos = (ox + TILE_SIZE - 8.5 + dx, oy + spec.y_center + dy)
        body = pymunk.Body(1, pymunk.moment_for_circle(1, 0, 8))
        body.position = pos
        body.velocity = (vx + dvx, vy + dvy)
        shape = pymunk.Circle(body, 8)
        shape.friction = .45; shape.elasticity = .55
        shape.collision_type = BALL_COLLISION_TYPE; shape.filter = ball_shape_filter()
        self.space.add(body, shape)
        self.balls.append(Ball(body, shape))

    def remove_ball(self, ball):
        try: self.space.remove(ball.shape, ball.body)
        except Exception: pass
        try: self.balls.remove(ball)
        except ValueError: pass


def start(canvas):
    global _preview, _last_ts
    _preview = EditorPreview()
    _last_ts = None

    def resize(_event=None):
        canvas.width = max(300, int(canvas.clientWidth))
        canvas.height = max(260, int(canvas.clientHeight))

    def click(_event=None):
        if _preview: _preview.spawn_boundary()

    resize_proxy = create_proxy(resize); click_proxy = create_proxy(click)
    _proxies.extend((resize_proxy, click_proxy))
    window.addEventListener("resize", resize_proxy)
    canvas.addEventListener("click", click_proxy)
    resize()

    def frame(ts):
        global _last_ts
        if not _paused:
            dt = 1/60 if _last_ts is None else max(0, min(.05, (ts-_last_ts)/1000))
            _last_ts = ts
            if _preview:
                _preview.step(dt); draw(canvas, _preview)
        window.requestAnimationFrame(frame_proxy)

    frame_proxy = create_proxy(frame); _proxies.append(frame_proxy)
    window.requestAnimationFrame(frame_proxy)


def refresh(route_index=0, mode="single"):
    global _preview
    if _preview is None:
        return
    _preview.configure(int(route_index), str(mode))


def set_paused(paused):
    """Pause physics and drawing while keeping the animation callback lightweight."""
    global _paused, _last_ts
    _paused = bool(paused)
    _last_ts = None
    return _paused


def draw(canvas, preview):
    ctx = canvas.getContext("2d")
    width, height = canvas.width, canvas.height
    ctx.fillStyle = "#f4e8c8"; ctx.fillRect(0, 0, width, height)
    world = preview.grid_size * TILE_SIZE
    scale = max(.3, min((width-36)/world, (height-44)/world))
    ox, oy = (width-world*scale)/2, (height-world*scale)/2
    sx=lambda x:ox+x*scale; sy=lambda y:oy+y*scale
    for _, _, builder in preview.owners:
        bx, by = builder.origin
        ctx.fillStyle="rgba(255,255,255,.2)";ctx.fillRect(sx(bx),sy(by),TILE_SIZE*scale,TILE_SIZE*scale)
        ctx.strokeStyle="rgba(91,78,52,.35)";ctx.lineWidth=1;ctx.strokeRect(sx(bx),sy(by),TILE_SIZE*scale,TILE_SIZE*scale)
        ctx.strokeStyle="#315aa8";ctx.lineCap="round"
        for shape in builder.visual_objects:
            if isinstance(shape,VisualSegment):
                ctx.beginPath();ctx.moveTo(sx(bx+shape.a[0]),sy(by+shape.a[1]));ctx.lineTo(sx(bx+shape.b[0]),sy(by+shape.b[1]));ctx.lineWidth=max(2,shape.radius*2*scale);ctx.stroke()
    if preview.mode == "single":
        _draw_port_overlays(ctx, preview.route, sx, sy, scale)
    for ball in preview.balls:
        p=ball.body.position;ctx.beginPath();ctx.arc(sx(p.x),sy(p.y),8*scale,0,math.tau)
        ctx.fillStyle="#1672d4";ctx.fill();ctx.strokeStyle="#0c3f8f";ctx.lineWidth=1.5;ctx.stroke()
    ctx.fillStyle="rgba(54,45,35,.78)";ctx.font="12px system-ui";ctx.fillText(f"{len(preview.balls)} balls · click to emit",12,height-12)
