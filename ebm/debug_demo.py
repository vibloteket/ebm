from __future__ import annotations

import math
import random

from js import window
from pyodide.ffi import create_proxy

from .ports import Port, PORT_SPECS, TILE_SIZE
from .tile_api import BALL_COLLISION_TYPE, BALL_ELASTICITY, BALL_FRICTION, TileBuilder, TileResourceRegistry, VisualSegment, ball_shape_filter
from .tile_catalog import default_tile
from .validator import _entry_base_velocity, validate_tile_port_spec


class _FlowContract:
    entries = (Port.T0, Port.L0, Port.R0)
    exits = (Port.B0, Port.L1, Port.R1)

    def __str__(self):
        return "Any input → any output"


FLOW_CONTRACT = _FlowContract()
_debug = None
_last_ts: float | None = None
_proxies = []


class DebugEngine:
    def __init__(self, contract_index: int = 0):
        import pymunk

        self.space = pymunk.Space()
        self.space.gravity = (0, 900)
        self.balls = []
        self.rng = random.Random(7)
        self.spawn_timer = 0.0
        self.validation = None
        self.set_contract(contract_index)

    @property
    def contract(self):
        return FLOW_CONTRACT

    def set_contract(self, index: int) -> None:
        index = 0
        for ball in list(getattr(self, "balls", [])):
            self.remove_ball(ball)
        if hasattr(self, "builder"):
            self.registry.destroy_owner(self.owner_id)

        self.contract_index = index
        self.tile = default_tile()
        self.registry = TileResourceRegistry.for_space(self.space)
        self.owner_id = index + 1
        self.builder = TileBuilder(self.registry, self.owner_id, (0, 0))
        self.tile.build(self.builder)
        self.spawn_timer = 0.0
        # Short validation for debug UI. The command-line validator uses stricter defaults.
        self.validation = validate_tile_port_spec(default_tile, duration=7.0)

    def step(self, dt: float) -> None:
        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            self.spawn_all_entries()
            self.spawn_timer = 0.8

        for _ in range(max(1, int(dt / (1 / 60)))):
            self.tile.update(self.builder, 1 / 60)
            self.space.step(1 / 60)

        for ball in list(self.balls):
            x, y = ball.body.position
            if x < -90 or x > TILE_SIZE + 90 or y < -90 or y > TILE_SIZE + 140:
                self.remove_ball(ball)

    def spawn_all_entries(self) -> None:
        for port in self.contract.entries:
            self.spawn_at_port(port)

    def spawn_at_port(self, port: Port) -> None:
        import pymunk

        BALL_RADIUS = 8
        spec = PORT_SPECS.get(port)
        if spec is not None:
            # Sample within the port spec ranges.
            dx = self.rng.uniform(-spec.x_range, spec.x_range)
            dy = self.rng.uniform(-spec.y_range, spec.y_range)
            dvx = self.rng.uniform(-spec.entry_vx_range, spec.entry_vx_range)
            dvy = self.rng.uniform(-spec.entry_vy_range, spec.entry_vy_range)
            base_vx, base_vy = _entry_base_velocity(port)

            if port == Port.T0:
                px = spec.x_center + dx
                py = spec.y_center + BALL_RADIUS + dy
                px = max(BALL_RADIUS + 0.5, min(200 - BALL_RADIUS - 0.5, px))
                py = max(BALL_RADIUS + 0.5, min(200 - BALL_RADIUS - 0.5, py))
            elif port == Port.L0:
                px = spec.x_center + BALL_RADIUS + dx
                py = spec.y_center + dy
                px = max(BALL_RADIUS + 0.5, min(200 - BALL_RADIUS - 0.5, px))
                py = max(BALL_RADIUS + 0.5, min(200 - BALL_RADIUS - 0.5, py))
            elif port == Port.R0:
                px = spec.x_center - BALL_RADIUS + dx
                py = spec.y_center + dy
                px = max(BALL_RADIUS + 0.5, min(200 - BALL_RADIUS - 0.5, px))
                py = max(BALL_RADIUS + 0.5, min(200 - BALL_RADIUS - 0.5, py))
            else:
                px = spec.x_center + dx
                py = spec.y_center + dy

            pos = (px, py)
            vel = (base_vx + dvx, base_vy + dvy)
        else:
            x, y = port.point
            if port == Port.T0:
                pos = (x + self.rng.uniform(-5, 5), y + 8)
                vel = (self.rng.uniform(-8, 8), 35)
            elif port == Port.L0:
                pos = (x + 8, y + self.rng.uniform(-5, 5))
                vel = (80, 10)
            elif port == Port.R0:
                pos = (x - 8, y + self.rng.uniform(-5, 5))
                vel = (-80, 10)
            else:
                pos = (x, y)
                vel = (0, 0)

        mass = 1
        radius = 8
        moment = pymunk.moment_for_circle(mass, 0, radius)
        body = pymunk.Body(mass, moment)
        body.position = pos
        body.velocity = vel
        body.sketch_seed = self.rng.randint(1, 999_999)
        shape = pymunk.Circle(body, radius)
        shape.friction = BALL_FRICTION
        shape.elasticity = BALL_ELASTICITY
        shape.collision_type = BALL_COLLISION_TYPE
        shape.filter = ball_shape_filter()
        self.space.add(body, shape)
        self.balls.append(Ball(body, shape))

    def remove_ball(self, ball) -> None:
        try:
            self.space.remove(ball.shape, ball.body)
        except Exception:
            pass
        try:
            self.balls.remove(ball)
        except ValueError:
            pass


class Ball:
    def __init__(self, body, shape):
        self.body = body
        self.shape = shape


def start(canvas, select, title_el=None, validation_el=None):
    global _debug, _last_ts
    _debug = DebugEngine(0)
    _last_ts = None
    _populate_select(select, title_el, validation_el)

    def resize(_event=None):
        width = max(320, int(canvas.clientWidth or window.innerWidth))
        height = max(240, int(canvas.clientHeight or window.innerHeight))
        canvas.width = width
        canvas.height = height

    def on_change(_event=None):
        if _debug is None:
            return
        _debug.set_contract(int(select.value))
        _update_title(title_el)
        _update_validation(validation_el)

    def on_click(_event=None):
        if _debug is not None:
            _debug.spawn_all_entries()

    select.addEventListener("change", create_proxy(on_change))
    canvas.addEventListener("click", create_proxy(on_click))
    resize_proxy = create_proxy(resize)
    _proxies.append(resize_proxy)
    window.addEventListener("resize", resize_proxy)
    resize()

    def frame(ts):
        global _last_ts
        if _debug is None:
            return
        dt = 1 / 60 if _last_ts is None else max(0.0, min(0.05, (ts - _last_ts) / 1000))
        _last_ts = ts
        _debug.step(dt)
        draw(canvas, _debug)
        window.requestAnimationFrame(frame_proxy)

    frame_proxy = create_proxy(frame)
    _proxies.append(frame_proxy)
    window.requestAnimationFrame(frame_proxy)


def _populate_select(select, title_el, validation_el=None) -> None:
    select.innerHTML = ""
    for i, contract in enumerate((FLOW_CONTRACT,)):
        option = window.document.createElement("option")
        option.value = str(i)
        option.textContent = _contract_label(contract)
        select.appendChild(option)
    _update_title(title_el)
    _update_validation(validation_el)


def _update_title(title_el) -> None:
    if title_el is not None and _debug is not None:
        title_el.textContent = _contract_label(_debug.contract)


def _update_validation(validation_el) -> None:
    if validation_el is None or _debug is None or _debug.validation is None:
        return
    result = _debug.validation
    validation_el.className = "validation-report ok" if result.ok else "validation-report fail"
    validation_el.textContent = (
        f"{'PASS' if result.ok else 'FAIL'}: "
        f"{result.exited}/{result.balls_spawned} exited, "
        f"{result.unexpected} unexpected, {result.out_of_bounds} out, "
        f"{result.stuck} stuck, {result.active} active"
    )


def _contract_label(contract) -> str:
    entries = ", ".join(port.name for port in contract.entries)
    exits = ", ".join(port.name for port in contract.exits)
    return f"{entries} → {exits}"


def draw(canvas, debug: DebugEngine) -> None:
    ctx = canvas.getContext("2d")
    width = canvas.width
    height = canvas.height
    ctx.fillStyle = "#f4e8c8"
    ctx.fillRect(0, 0, width, height)

    toolbar = window.document.getElementById("debug-toolbar")
    toolbar_height = toolbar.getBoundingClientRect().height if toolbar is not None else 0
    bottom_padding = 34
    top_padding = toolbar_height + 20
    available_height = max(160, height - top_padding - bottom_padding)
    scale = min((width - 48) / TILE_SIZE, available_height / TILE_SIZE)
    scale = max(0.8, min(scale, 3.2))
    ox = (width - TILE_SIZE * scale) / 2
    oy = top_padding + (available_height - TILE_SIZE * scale) / 2

    def sx(x): return ox + x * scale
    def sy(y): return oy + y * scale

    # Tile box and port zones.
    ctx.fillStyle = "rgba(255,255,255,0.18)"
    ctx.fillRect(sx(0), sy(0), TILE_SIZE * scale, TILE_SIZE * scale)
    ctx.strokeStyle = "rgba(91, 78, 52, 0.40)"
    ctx.lineWidth = 2
    ctx.strokeRect(sx(0), sy(0), TILE_SIZE * scale, TILE_SIZE * scale)

    _draw_port_overlays(ctx, sx, sy, scale)

    # Plain diagnostic rendering: solid route lines and balls.
    ctx.lineCap = "round"
    ctx.strokeStyle = "#315aa8"
    for shape in debug.builder.visual_objects:
        if isinstance(shape, VisualSegment):
            ctx.beginPath();ctx.moveTo(sx(shape.a[0]),sy(shape.a[1]));ctx.lineTo(sx(shape.b[0]),sy(shape.b[1]))
            ctx.lineWidth=max(3,shape.radius*2*scale);ctx.stroke()

    for ball in debug.balls:
        p=ball.body.local_to_world(ball.shape.offset)
        ctx.beginPath();ctx.arc(sx(p.x),sy(p.y),ball.shape.radius*scale,0,math.tau)
        ctx.fillStyle="#1672d4";ctx.fill();ctx.strokeStyle="#0c3f8f";ctx.lineWidth=2;ctx.stroke()

    ctx.fillStyle="rgba(54,45,35,.78)";ctx.font="12px system-ui, sans-serif"
    ctx.fillText(f"balls: {len(debug.balls)} | click tile to spawn",14,height-18)


BALL_RADIUS = 8


def _draw_port_overlays(ctx, sx, sy, scale) -> None:
    for port in (Port.T0, Port.L0, Port.R0):
        _draw_port_spec_zone(ctx, port, sx, sy, scale, kind="entry")
    for port in (Port.B0, Port.L1, Port.R1):
        _draw_port_spec_zone(ctx, port, sx, sy, scale, kind="exit")


def _draw_port_spec_zone(ctx, port: Port, sx, sy, scale: float, kind: str) -> None:
    spec = PORT_SPECS.get(port)
    if spec is None:
        return

    fill = "rgba(34,197,94,0.28)" if kind == "entry" else "rgba(239,68,68,0.28)"
    stroke_color = "#86efac" if kind == "entry" else "#fca5a5"

    # Build a polygon that shows the position range.
    hw = spec.x_range * scale
    hh = spec.y_range * scale
    cx = sx(spec.x_center)
    cy = sy(spec.y_center)

    if port in (Port.T0, Port.B0):
        # Vertical port: draw a rectangle that spans the x_range and a thin y strip.
        if port == Port.T0:
            top = sy(spec.y_center + BALL_RADIUS - spec.y_range)
            bot = sy(spec.y_center + BALL_RADIUS + spec.y_range)
        else:
            top = sy(spec.y_center - spec.y_range)
            bot = sy(spec.y_center + spec.y_range)
        left = cx - hw
        right = cx + hw
        ctx.fillStyle = fill
        ctx.strokeStyle = stroke_color
        ctx.lineWidth = max(1.5, 2 * scale)
        ctx.beginPath()
        ctx.rect(left, min(top, bot), right - left, abs(bot - top))
        ctx.fill()
        ctx.stroke()
    elif port in (Port.L0, Port.L1):
        # Horizontal left-side port.
        if port == Port.L0:
            left = sx(spec.x_center + BALL_RADIUS - spec.x_range)
            right = sx(spec.x_center + BALL_RADIUS + spec.x_range)
        else:
            left = sx(spec.x_center - spec.x_range)
            right = sx(spec.x_center + spec.x_range)
        top = cy - hh
        bot = cy + hh
        ctx.fillStyle = fill
        ctx.strokeStyle = stroke_color
        ctx.lineWidth = max(1.5, 2 * scale)
        ctx.beginPath()
        ctx.rect(min(left, right), top, abs(right - left), bot - top)
        ctx.fill()
        ctx.stroke()
    elif port in (Port.R0, Port.R1):
        # Horizontal right-side port.
        if port == Port.R0:
            left = sx(spec.x_center - BALL_RADIUS - spec.x_range)
            right = sx(spec.x_center - BALL_RADIUS + spec.x_range)
        else:
            left = sx(spec.x_center - spec.x_range)
            right = sx(spec.x_center + spec.x_range)
        top = cy - hh
        bot = cy + hh
        ctx.fillStyle = fill
        ctx.strokeStyle = stroke_color
        ctx.lineWidth = max(1.5, 2 * scale)
        ctx.beginPath()
        ctx.rect(min(left, right), top, abs(right - left), bot - top)
        ctx.fill()
        ctx.stroke()

    # Port label
    ctx.fillStyle = stroke_color
    ctx.font = f"{max(10, int(11 * scale))}px system-ui, sans-serif"
    ctx.textAlign = "center"
    ctx.textBaseline = "middle"
    label_x = cx
    label_y = cy
    if port == Port.T0:
        label_y = sy(spec.y_center + BALL_RADIUS + spec.y_range + 10)
    elif port == Port.B0:
        label_y = sy(spec.y_center - spec.y_range - 10)
    elif port == Port.L0:
        label_x = sx(spec.x_center + BALL_RADIUS + spec.x_range + 12)
    elif port == Port.L1:
        label_x = sx(spec.x_center - spec.x_range - 12)
    elif port == Port.R0:
        label_x = sx(spec.x_center - BALL_RADIUS - spec.x_range - 12)
    elif port == Port.R1:
        label_x = sx(spec.x_center + spec.x_range + 12)
    ctx.fillText(port.name, label_x, label_y)
    ctx.textAlign = "start"
    ctx.textBaseline = "alphabetic"


