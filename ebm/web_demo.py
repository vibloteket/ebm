from __future__ import annotations

import json
import time

from js import window, document
from pyodide.ffi import to_js
from pyodide.ffi import create_proxy

from .engine import Engine
from .ports import TILE_SIZE
from .tile_api import VisualSegment
from . import pigment

_engine: Engine | None = None
_last_ts: float | None = None
_dragging = False
_drag_start = (0.0, 0.0)
_last_pointer = (0.0, 0.0)
_moved = False
_static_dirty = True
_last_dynamic_draw = 0.0
_frame_samples: list[float] = []
_tile_cache = {}
_renderer = "basic"
_TILE_PAD = 14
_TILE_SCALE = 2
_render_profile = {
    "raf_frames": 0,
    "dynamic_frames": 0,
    "static_frames": 0,
    "dynamic_total_ms": 0.0,
    "dynamic_max_ms": 0.0,
    "static_total_ms": 0.0,
    "static_max_ms": 0.0,
    "cache_hits": 0,
    "cache_misses": 0,
}
_proxies = []


def set_renderer(name):
    global _renderer, _static_dirty
    value = str(name)
    _renderer = value if value in ("basic", "v3") else "basic"
    _static_dirty = True


def renderer_value():
    return _renderer


def zoom_at(cx, cy, factor):
    global _static_dirty
    if _engine is not None:
        _engine.zoom_at(cx, cy, factor)
        _static_dirty = True


def set_zoom(value):
    global _static_dirty
    if _engine is not None:
        _engine.set_zoom_at(_engine.viewport.width/2, _engine.viewport.height/2, float(value))
        _static_dirty = True


def zoom_value():
    return _engine.viewport.zoom if _engine is not None else .5


def performance_stats():
    """Return and reset one profiling window as JSON for the web overlay."""
    if _engine is None:
        return "{}"
    snapshot = dict(_render_profile)
    snapshot["engine"] = _engine.consume_profile()
    snapshot["tiles"] = len(_engine.active_tiles)
    snapshot["visible_tiles"] = len({
        (row, col)
        for row in range(__import__("math").floor(_engine.viewport.y / TILE_SIZE), __import__("math").floor((_engine.viewport.bottom - 1e-6) / TILE_SIZE) + 1)
        for col in range(__import__("math").floor(_engine.viewport.x / TILE_SIZE), __import__("math").floor((_engine.viewport.right - 1e-6) / TILE_SIZE) + 1)
    })
    snapshot["boundary_inputs"] = len(_engine._spawn_clocks)
    snapshot["balls"] = len(_engine.balls)
    snapshot["shapes"] = len(_engine.space.shapes)
    snapshot["bodies"] = len(_engine.space.bodies)
    snapshot["constraints"] = len(_engine.space.constraints)
    snapshot["tile_cache_entries"] = len(_tile_cache)
    for key in list(_render_profile):
        _render_profile[key] = 0 if key.endswith(("frames", "hits", "misses")) else 0.0
    return json.dumps(snapshot)


def start(static_canvas, dynamic_canvas):
    global _engine, _last_ts, _static_dirty
    _engine = Engine(dynamic_canvas.width, dynamic_canvas.height)
    _last_ts = None
    _static_dirty = True

    def resize(_event=None):
        global _static_dirty
        width = max(320, int(dynamic_canvas.clientWidth or window.innerWidth))
        height = max(240, int(dynamic_canvas.clientHeight or window.innerHeight))
        for canvas in (static_canvas, dynamic_canvas):
            canvas.width = width
            canvas.height = height
        if _engine:
            _engine.resize(width, height)
        _static_dirty = True

    def pointer_down(event):
        global _dragging, _drag_start, _last_pointer, _moved
        _dragging = True; _moved = False
        _drag_start = (event.clientX, event.clientY)
        _last_pointer = (event.clientX, event.clientY)
        try: dynamic_canvas.setPointerCapture(event.pointerId)
        except Exception: pass

    def pointer_move(event):
        global _last_pointer, _moved, _static_dirty
        if not _dragging or _engine is None: return
        x, y = event.clientX, event.clientY
        lx, ly = _last_pointer
        if abs(x-_drag_start[0]) + abs(y-_drag_start[1]) > 4: _moved = True
        _engine.pan(-(x-lx), -(y-ly)); _last_pointer = (x, y); _static_dirty = True

    def pointer_up(event):
        global _dragging
        if _engine is None: return
        _dragging = False
        if not _moved:
            rect = dynamic_canvas.getBoundingClientRect()
            wx, wy = _engine.screen_to_world(event.clientX-rect.left, event.clientY-rect.top)
            _engine.add_ball(wx, wy)

    def key_down(event):
        global _static_dirty
        if _engine is None: return
        step = 70
        if event.key == "ArrowLeft": _engine.pan(-step, 0)
        elif event.key == "ArrowRight": _engine.pan(step, 0)
        elif event.key == "ArrowUp": _engine.pan(0, -step)
        elif event.key == "ArrowDown": _engine.pan(0, step)
        elif event.key in ("+", "="): _engine.zoom_at(_engine.viewport.width/2, _engine.viewport.height/2, 1.2)
        elif event.key in ("-", "_"): _engine.zoom_at(_engine.viewport.width/2, _engine.viewport.height/2, 1/1.2)
        elif event.key == "0": _engine.set_zoom_at(_engine.viewport.width/2, _engine.viewport.height/2, .5)
        else: return
        event.preventDefault(); _static_dirty = True

    def wheel(event):
        global _static_dirty
        if _engine is None: return
        event.preventDefault()
        rect = dynamic_canvas.getBoundingClientRect()
        _engine.zoom_at(event.clientX-rect.left, event.clientY-rect.top, 1.0+event.deltaY*-0.001)
        _static_dirty = True

    handlers = [pointer_down, pointer_move, pointer_up, key_down, resize, wheel]
    proxies = [create_proxy(handler) for handler in handlers]
    _proxies.extend(proxies)
    dynamic_canvas.addEventListener("pointerdown", proxies[0])
    dynamic_canvas.addEventListener("pointermove", proxies[1])
    dynamic_canvas.addEventListener("pointerup", proxies[2])
    dynamic_canvas.addEventListener("pointercancel", proxies[2])
    window.addEventListener("keydown", proxies[3]); window.addEventListener("resize", proxies[4])
    dynamic_canvas.addEventListener("wheel", proxies[5], {"passive": False})
    resize()

    frame_proxy = None
    def frame(ts):
        global _last_ts, _static_dirty, _last_dynamic_draw
        if _engine is None: return
        _render_profile["raf_frames"] += 1
        dt = 1/60 if _last_ts is None else max(0.0, min(.05, (ts-_last_ts)/1000))
        _last_ts = ts; _engine.step_frame(dt)
        if _static_dirty:
            started=time.perf_counter(); draw_static(static_canvas, _engine)
            elapsed=(time.perf_counter()-started)*1000
            _render_profile["static_frames"] += 1
            _render_profile["static_total_ms"] += elapsed
            _render_profile["static_max_ms"] = max(_render_profile["static_max_ms"],elapsed)
            _static_dirty = False
        # Firefox spends far less time compositing at a stable 30 FPS than at
        # an uneven 40–60 FPS. Physics still advances every animation frame.
        if ts - _last_dynamic_draw >= 1000/30:
            started=time.perf_counter(); draw_dynamic(dynamic_canvas, _engine)
            elapsed=(time.perf_counter()-started)*1000
            _render_profile["dynamic_frames"] += 1
            _render_profile["dynamic_total_ms"] += elapsed
            _render_profile["dynamic_max_ms"] = max(_render_profile["dynamic_max_ms"],elapsed)
            _last_dynamic_draw = ts
        window.requestAnimationFrame(frame_proxy)

    frame_proxy = create_proxy(frame); _proxies.append(frame_proxy); window.requestAnimationFrame(frame_proxy)


def _transform(ctx, engine):
    zoom = engine.viewport.zoom
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height)
    ctx.scale(zoom, zoom)
    return engine.viewport.x, engine.viewport.y, zoom


def draw_static(canvas, engine: Engine):
    ctx = canvas.getContext("2d"); vx, vy, zoom = _transform(ctx, engine)
    width, height = canvas.width/zoom, canvas.height/zoom
    pigment.paper(ctx, width, height); pigment.grid(ctx, vx, vy, width, height, TILE_SIZE)
    for active in engine.active_tiles.values():
        tile_canvas = _cached_tile(active)
        ox, oy = active.builder.origin
        size = TILE_SIZE + _TILE_PAD*2
        ctx.drawImage(tile_canvas, ox-vx-_TILE_PAD, oy-vy-_TILE_PAD, size, size)


def _cached_tile(active):
    # Three deterministic visual variants avoid an obvious repeated bitmap,
    # while retaining almost all of the benefit of caching by contract.
    row=int(active.builder.origin[1]//TILE_SIZE);col=int(active.builder.origin[0]//TILE_SIZE)
    variant = (row*31 + col*17) % 3
    key = (_renderer, active.tile.route.key, variant)
    cached = _tile_cache.get(key)
    if cached is not None:
        _render_profile["cache_hits"] += 1
        return cached
    _render_profile["cache_misses"] += 1

    size = TILE_SIZE + _TILE_PAD*2
    ox, oy = active.builder.origin
    segments, circles, polygons = [], [], []
    for shape in active.builder.visual_objects:
        if isinstance(shape, VisualSegment):
            segments.append([shape.a[0]+_TILE_PAD,shape.a[1]+_TILE_PAD,shape.b[0]+_TILE_PAD,shape.b[1]+_TILE_PAD,shape.radius])
            continue
        if not hasattr(shape, "body") or shape.body.body_type != 2 or getattr(shape, "ebm_hidden", False): continue
        name = type(shape).__name__
        if name == "Segment":
            a, b = shape.body.local_to_world(shape.a), shape.body.local_to_world(shape.b)
            segments.append([a.x-ox+_TILE_PAD,a.y-oy+_TILE_PAD,b.x-ox+_TILE_PAD,b.y-oy+_TILE_PAD,shape.radius])
        elif name == "Circle":
            p=shape.body.local_to_world(shape.offset);circles.append([p.x-ox+_TILE_PAD,p.y-oy+_TILE_PAD,shape.radius])
        elif name == "Poly":
            vertices=[shape.body.local_to_world(v) for v in shape.get_vertices()]
            polygons.append([(v.x-ox+_TILE_PAD,v.y-oy+_TILE_PAD) for v in vertices])

    if _renderer == "basic":
        canvas=document.createElement("canvas");canvas.width=size;canvas.height=size
        ctx=canvas.getContext("2d");ctx.lineCap="round";ctx.strokeStyle="#315aa8"
        for x1,y1,x2,y2,radius in segments:
            ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.lineWidth=max(3,radius*2);ctx.stroke()
        ctx.fillStyle="#dc7625";ctx.strokeStyle="#8c4318";ctx.lineWidth=2
        for x,y,radius in circles:
            ctx.beginPath();ctx.arc(x,y,radius,0,__import__("math").tau);ctx.fill();ctx.stroke()
    else:
        # Bake blue rails and orange bumpers separately, then composite once.
        rail_canvas=window.renderV3Tile(to_js(segments),to_js([]),1.7+variant*2.3,size,1,to_js([.075,.19,.49]))
        bumper_canvas=window.renderV3Tile(to_js([]),to_js(circles),4.2+variant*2.3,size,1,to_js([.86,.31,.055]))
        canvas=document.createElement("canvas");canvas.width=size;canvas.height=size
        composite=canvas.getContext("2d")
        if rail_canvas is not None: composite.drawImage(rail_canvas,0,0,size,size)
        if bumper_canvas is not None: composite.drawImage(bumper_canvas,0,0,size,size)
        if rail_canvas is None and bumper_canvas is None: canvas=None
        if canvas is None:
            canvas=document.createElement("canvas");canvas.width=size;canvas.height=size
            ctx=canvas.getContext("2d")
            for x1,y1,x2,y2,radius in segments:pigment.segment(ctx,x1,y1,x2,y2,radius,_seed(x1,y1,x2,y2,radius,variant))
            for x,y,radius in circles:pigment.circle(ctx,x,y,radius,_seed(x,y,radius,variant))
    # Polygons are uncommon in the current fillers; retain the Canvas material
    # overlay until the shader gains polygon SDF support.
    if polygons:
        ctx=canvas.getContext("2d")
        if ctx is not None:
            for points in polygons:pigment.polygon(ctx,points,_seed(*[c for point in points for c in point],variant))
    _tile_cache[key] = canvas
    return canvas


def draw_dynamic(canvas, engine: Engine):
    ctx = canvas.getContext("2d"); vx, vy, zoom = _transform(ctx, engine)
    # Balls are already tracked by Engine. Avoid scanning every static Pymunk
    # shape on every dynamic frame; full-screen 0.5× views contain thousands.
    for ball_item in engine.balls:
        shape, body = ball_item.shape, ball_item.body
        p = body.local_to_world(shape.offset)
        if _renderer == "basic":
            ctx.beginPath();ctx.arc(p.x-vx,p.y-vy,shape.radius,0,__import__("math").tau)
            ctx.fillStyle="#1672d4";ctx.fill();ctx.strokeStyle="#0c3f8f";ctx.lineWidth=2;ctx.stroke()
        else:
            pigment.ball(ctx, p.x-vx, p.y-vy, shape.radius, getattr(body,"sketch_seed",_seed(p.x,p.y)))


def _seed(*values) -> int:
    total=sum((i+1)*97.13*round(float(v),2) for i,v in enumerate(values))
    return int(abs(__import__("math").sin(total))*1_000_000)+1
