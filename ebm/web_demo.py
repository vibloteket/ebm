"""Browser entry point: physics stepping, input, and scene export.

All drawing lives in ``web/scene.js``. This module steps the engine, mirrors
scene changes through :class:`~ebm.scene_export.SceneExporter`, and forwards
one pose buffer per animation frame. Keeping canvas work in JavaScript avoids
thousands of Pyodide proxy calls per second in the hot loop.
"""

import json
import time

from js import window
from pyodide.ffi import to_js
from pyodide.ffi import create_proxy

from .engine import Engine
from .ports import TILE_SIZE
from .scene_export import SceneExporter

_engine: Engine | None = None
_exporter: SceneExporter | None = None
_last_ts: float | None = None
_dragging = False
_drag_start = (0.0, 0.0)
_last_pointer = (0.0, 0.0)
_moved = False
_render_profile = {
    "raf_frames": 0,
    "export_calls": 0,
    "export_total_ms": 0.0,
    "export_max_ms": 0.0,
    "sync_events": 0,
}
_proxies = []

def zoom_at(cx, cy, factor):
    if _engine is not None:
        _engine.zoom_at(cx, cy, factor)

def set_zoom(value):
    if _engine is not None:
        _engine.set_zoom_at(_engine.viewport.width/2, _engine.viewport.height/2, float(value))

def zoom_value():
    return _engine.viewport.zoom if _engine is not None else .5

def set_tile_profiling(enabled):
    """Toggle per-tile-type update() timing (enabled while the stats overlay shows)."""
    if _engine is not None:
        _engine.set_tile_profiling(bool(enabled))

def performance_stats():
    """Return and reset one profiling window as JSON for the web overlay."""
    if _engine is None:
        return "{}"
    snapshot = dict(_render_profile)
    snapshot["engine"] = _engine.consume_profile()
    snapshot["per_tile"] = _engine.consume_tile_profile()
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
    for key in list(_render_profile):
        _render_profile[key] = 0 if key.endswith(("frames", "calls", "events")) else 0.0
    return json.dumps(snapshot)

def start(static_canvas, dynamic_canvas):
    global _engine, _exporter, _last_ts
    _engine = Engine(dynamic_canvas.width, dynamic_canvas.height)
    _exporter = SceneExporter(_engine)
    _last_ts = None
    window.EbmScene.attach(static_canvas, dynamic_canvas)

    def resize(_event=None):
        width = max(320, int(dynamic_canvas.clientWidth or window.innerWidth))
        height = max(240, int(dynamic_canvas.clientHeight or window.innerHeight))
        for canvas in (static_canvas, dynamic_canvas):
            canvas.width = width
            canvas.height = height
        if _engine:
            _engine.resize(width, height)

    def pointer_down(event):
        global _dragging, _drag_start, _last_pointer, _moved
        _dragging = True; _moved = False
        _drag_start = (event.clientX, event.clientY)
        _last_pointer = (event.clientX, event.clientY)
        try: dynamic_canvas.setPointerCapture(event.pointerId)
        except Exception: pass

    def pointer_move(event):
        global _last_pointer, _moved
        if not _dragging or _engine is None: return
        x, y = event.clientX, event.clientY
        lx, ly = _last_pointer
        if abs(x-_drag_start[0]) + abs(y-_drag_start[1]) > 4: _moved = True
        _engine.pan(-(x-lx), -(y-ly)); _last_pointer = (x, y)

    def pointer_up(event):
        global _dragging
        if _engine is None: return
        _dragging = False
        if not _moved:
            rect = dynamic_canvas.getBoundingClientRect()
            wx, wy = _engine.screen_to_world(event.clientX-rect.left, event.clientY-rect.top)
            _engine.add_ball(wx, wy)

    def key_down(event):
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
        event.preventDefault()

    def wheel(event):
        if _engine is None: return
        event.preventDefault()
        rect = dynamic_canvas.getBoundingClientRect()
        _engine.zoom_at(event.clientX-rect.left, event.clientY-rect.top, 1.0+event.deltaY*-0.001)

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
        global _last_ts
        if _engine is None or _exporter is None: return
        _render_profile["raf_frames"] += 1
        dt = 1/60 if _last_ts is None else max(0.0, min(.05, (ts-_last_ts)/1000))
        _last_ts = ts; _engine.step_frame(dt)
        started = time.perf_counter()
        events = _exporter.sync()
        ids, floats, id_stride = _exporter.frame()
        viewport = _engine.viewport
        window.EbmScene.frame(
            to_js(events), viewport.x, viewport.y, viewport.zoom,
            to_js(ids), to_js(floats), id_stride,
        )
        elapsed = (time.perf_counter()-started)*1000
        _render_profile["export_calls"] += 1
        _render_profile["export_total_ms"] += elapsed
        _render_profile["export_max_ms"] = max(_render_profile["export_max_ms"], elapsed)
        _render_profile["sync_events"] += len(events)
        window.requestAnimationFrame(frame_proxy)

    frame_proxy = create_proxy(frame); _proxies.append(frame_proxy); window.requestAnimationFrame(frame_proxy)
