from __future__ import annotations

import math

try:
    from js import Object, rough
    from pyodide.ffi import to_js
except Exception:  # non-browser imports/tests
    Object = None
    rough = None
    to_js = None

# rough.js test renderer. Goal: evaluate whether a real hand-drawn primitive
# library gets closer to Crayon Physics than our hand-rolled canvas jitter.
PAPER = "#f7efcf"
RAIL = "#2a3d8b"
RAIL_EDGE = "#192358"
BLUE = "#1f75fe"
BLUE_EDGE = "#134aab"
BLUE_LIGHT = "rgba(164, 211, 255, 0.58)"
BUMPER = "#f28c28"
BUMPER_EDGE = "#9f5215"
POLY_FILL = "#469b71"
POLY_EDGE = "#225d43"
TEXT = "rgba(54, 45, 35, 0.78)"


_rough_by_canvas = {}


def draw_paper(ctx, width: float, height: float) -> None:
    ctx.fillStyle = PAPER
    ctx.fillRect(0, 0, width, height)

    gradient = ctx.createRadialGradient(width / 2, height / 2, 0, width / 2, height / 2, max(width, height) * 0.75)
    gradient.addColorStop(0, "rgba(255,255,255,0.00)")
    gradient.addColorStop(1, "rgba(174,129,59,0.09)")
    ctx.fillStyle = gradient
    ctx.fillRect(0, 0, width, height)


def draw_tile_grid(ctx, vx: float, vy: float, width: float, height: float, tile_size: int) -> None:
    start_x = math.floor(vx / tile_size) * tile_size
    start_y = math.floor(vy / tile_size) * tile_size
    ctx.strokeStyle = "rgba(86, 70, 43, 0.030)"
    ctx.lineWidth = 1
    x = start_x
    while x <= vx + width + tile_size:
        sx = x - vx
        ctx.beginPath()
        ctx.moveTo(sx, 0)
        ctx.lineTo(sx, height)
        ctx.stroke()
        x += tile_size
    y = start_y
    while y <= vy + height + tile_size:
        sy = y - vy
        ctx.beginPath()
        ctx.moveTo(0, sy)
        ctx.lineTo(width, sy)
        ctx.stroke()
        y += tile_size


def draw_segment(ctx, x1: float, y1: float, x2: float, y2: float, radius: float, scale: float = 1.0, color: str = RAIL, seed: int | None = None) -> None:
    rc = _rough_canvas(ctx)
    seed = seed if seed is not None else _seed(x1, y1, x2, y2, radius)
    width = max(7.0 * scale, radius * 3.8 * scale)

    if rc is None:
        _fallback_line(ctx, x1, y1, x2, y2, width, color)
        return

    # Two rough.js lines: a broad pale wax body and a darker kid-crayon stroke.
    rc.line(x1, y1, x2, y2, _opts({
        "seed": seed,
        "stroke": "rgba(91, 119, 205, 0.24)",
        "strokeWidth": width + 3.5 * scale,
        "roughness": 1.7,
        "bowing": 1.4,
        "disableMultiStroke": False,
    }))
    rc.line(x1, y1, x2, y2, _opts({
        "seed": seed + 101,
        "stroke": color,
        "strokeWidth": width,
        "roughness": 1.25,
        "bowing": 1.0,
        "disableMultiStroke": False,
    }))
    # A thin darker outline pass helps segments read as physical rails.
    rc.line(x1, y1, x2, y2, _opts({
        "seed": seed + 202,
        "stroke": RAIL_EDGE,
        "strokeWidth": max(1.2, 1.6 * scale),
        "roughness": 1.4,
        "bowing": 1.2,
    }))


def draw_ball(ctx, x: float, y: float, radius: float, scale: float = 1.0, seed: int | None = None) -> None:
    rc = _rough_canvas(ctx)
    seed = seed if seed is not None else _seed(round(x / 4), round(y / 4), radius)
    diameter = radius * 2 * scale
    if rc is None:
        _fallback_circle(ctx, x, y, radius * scale, BLUE, BLUE_EDGE)
        return

    rc.circle(x, y, diameter, _opts({
        "seed": seed,
        "stroke": BLUE_EDGE,
        "strokeWidth": max(1.8, 2.1 * scale),
        "fill": BLUE,
        "fillStyle": "solid",
        "fillWeight": max(1.0, 1.5 * scale),
        "roughness": 1.05,
        "bowing": 0.9,
    }))
    ctx.beginPath()
    ctx.arc(x - radius * scale * 0.33, y - radius * scale * 0.35, max(1.2, radius * scale * 0.22), 0, math.tau)
    ctx.fillStyle = BLUE_LIGHT
    ctx.fill()


def draw_bumper(ctx, x: float, y: float, radius: float, scale: float = 1.0, seed: int | None = None) -> None:
    rc = _rough_canvas(ctx)
    seed = seed if seed is not None else _seed(x, y, radius, 33)
    if rc is None:
        _fallback_circle(ctx, x, y, radius * scale, BUMPER, BUMPER_EDGE)
        return
    rc.circle(x, y, radius * 2 * scale, _opts({
        "seed": seed,
        "stroke": BUMPER_EDGE,
        "strokeWidth": max(1.8, 2.2 * scale),
        "fill": BUMPER,
        "fillStyle": "hachure",
        "hachureGap": max(3.0, 4.0 * scale),
        "fillWeight": max(1.2, 1.8 * scale),
        "roughness": 1.25,
        "bowing": 1.0,
    }))


def draw_poly(ctx, points: list[tuple[float, float]], scale: float = 1.0, seed: int | None = None) -> None:
    if not points:
        return
    rc = _rough_canvas(ctx)
    seed = seed if seed is not None else _seed(*[coord for p in points for coord in p[:2]])
    if rc is None:
        ctx.beginPath()
        ctx.moveTo(points[0][0], points[0][1])
        for x, y in points[1:]:
            ctx.lineTo(x, y)
        ctx.closePath()
        ctx.fillStyle = "rgba(70,155,113,0.40)"
        ctx.fill()
        ctx.strokeStyle = POLY_EDGE
        ctx.stroke()
        return
    rc.polygon(_points(points), _opts({
        "seed": seed,
        "stroke": POLY_EDGE,
        "strokeWidth": max(1.6, 2.0 * scale),
        "fill": POLY_FILL,
        "fillStyle": "hachure",
        "hachureGap": max(4.0, 5.0 * scale),
        "fillWeight": max(1.0, 1.4 * scale),
        "roughness": 1.2,
        "bowing": 0.8,
    }))


def draw_text(ctx, text: str, x: float, y: float, size: int = 12) -> None:
    ctx.fillStyle = TEXT
    ctx.font = f"{size}px 'Comic Sans MS', 'Comic Sans', 'Marker Felt', 'Bradley Hand', system-ui, sans-serif"
    ctx.fillText(text, x, y)


def _rough_canvas(ctx):
    if rough is None:
        return None
    canvas = ctx.canvas
    key = getattr(canvas, "id", "") or "canvas"
    # Reusing the rough canvas object avoids recreating its generator for every
    # shape. The key is enough here because the app uses one canvas per page.
    rc = _rough_by_canvas.get(key)
    if rc is None:
        rc = rough.canvas(canvas)
        _rough_by_canvas[key] = rc
    return rc


def _opts(value: dict):
    if to_js is None or Object is None:
        return value
    return to_js(value, dict_converter=Object.fromEntries)


def _points(points: list[tuple[float, float]]):
    if to_js is None:
        return points
    return to_js([[x, y] for x, y in points])


def _fallback_line(ctx, x1: float, y1: float, x2: float, y2: float, width: float, color: str) -> None:
    ctx.beginPath()
    ctx.moveTo(x1, y1)
    ctx.lineTo(x2, y2)
    ctx.lineWidth = width
    ctx.lineCap = "round"
    ctx.strokeStyle = color
    ctx.stroke()


def _fallback_circle(ctx, x: float, y: float, radius: float, fill: str, edge: str) -> None:
    ctx.beginPath()
    ctx.arc(x, y, radius, 0, math.tau)
    ctx.fillStyle = fill
    ctx.fill()
    ctx.lineWidth = 2
    ctx.strokeStyle = edge
    ctx.stroke()


def stable_seed(*values: float) -> int:
    total = 0.0
    for i, value in enumerate(values):
        total += (i + 1) * 97.13 * round(float(value), 2)
    # rough.js wants a positive integer seed.
    return int(abs(math.sin(total) * 1_000_000)) + 1


def _seed(*values: float) -> int:
    return stable_seed(*values)
