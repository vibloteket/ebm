from __future__ import annotations

import math
import random

try:
    from js import document
except Exception:  # pragma: no cover - browser-only rendering
    document = None

PAPER = "#f4e8c8"
BLUE = "#173f91"
BLUE_DARK = "#102d6d"
ORANGE = "#d96c20"
ORANGE_DARK = "#913f13"
GREEN = "#39835f"
GREEN_DARK = "#20543c"
TEXT = "rgba(54,45,35,.76)"

_ball_sprites: dict[tuple[int, int], object] = {}


def paper(ctx, width: float, height: float) -> None:
    ctx.fillStyle = PAPER
    ctx.fillRect(0, 0, width, height)
    gradient = ctx.createRadialGradient(width * .5, height * .45, 0, width * .5, height * .45, max(width, height) * .75)
    gradient.addColorStop(0, "rgba(255,255,255,.08)")
    gradient.addColorStop(1, "rgba(111,76,30,.08)")
    ctx.fillStyle = gradient
    ctx.fillRect(0, 0, width, height)


def grid(ctx, vx: float, vy: float, width: float, height: float, tile_size: int) -> None:
    start_x = math.floor(vx / tile_size) * tile_size
    start_y = math.floor(vy / tile_size) * tile_size
    ctx.strokeStyle = "rgba(86,70,43,.035)"
    ctx.lineWidth = 1
    x = start_x
    while x <= vx + width + tile_size:
        sx = x - vx
        ctx.beginPath(); ctx.moveTo(sx, 0); ctx.lineTo(sx, height); ctx.stroke()
        x += tile_size
    y = start_y
    while y <= vy + height + tile_size:
        sy = y - vy
        ctx.beginPath(); ctx.moveTo(0, sy); ctx.lineTo(width, sy); ctx.stroke()
        y += tile_size


def segment(ctx, x1: float, y1: float, x2: float, y2: float, radius: float, seed: int, color: str = BLUE) -> None:
    """Deterministic V3-derived crayon stroke with a broken silhouette."""
    rnd = random.Random(seed)
    dx, dy = x2 - x1, y2 - y1
    length = max(1.0, math.hypot(dx, dy))
    nx, ny = -dy / length, dx / length
    width = max(8.0, radius * 3.8)

    # Narrow intermittent core: readable, but never a ruler-straight outline.
    pieces = max(2, int(length / 24))
    ctx.lineCap = "round"
    for i in range(pieces):
        if rnd.random() < .13:
            continue
        ta = i / pieces + rnd.uniform(-.015, .012)
        tb = min(1.0, (i + 1) / pieces + rnd.uniform(-.012, .018))
        wobble = rnd.uniform(-width * .09, width * .09)
        ctx.beginPath()
        ctx.moveTo(x1 + dx * ta + nx * wobble, y1 + dy * ta + ny * wobble)
        ctx.lineTo(x1 + dx * tb - nx * wobble * .35, y1 + dy * tb - ny * wobble * .35)
        ctx.strokeStyle = color
        ctx.globalAlpha = rnd.uniform(.52, .78)
        ctx.lineWidth = width * rnd.uniform(.62, .86)
        ctx.stroke()

    # Fractal-like clusters at three scales break both body and silhouette.
    for scale, spacing, alpha in ((1.0, 8.5, .28), (.55, 4.5, .22), (.25, 2.6, .18)):
        count = max(2, int(length / spacing))
        phase = rnd.random() * math.tau
        for i in range(count):
            t = (i + rnd.random()) / count
            branch = math.sin(t * math.tau * (2.0 + scale) + phase) + .55 * math.sin(t * math.tau * 7.0 - phase)
            spread = branch * width * .26 + rnd.uniform(-width * .48, width * .48)
            if rnd.random() < .17:
                continue
            x = x1 + dx * t + nx * spread
            y = y1 + dy * t + ny * spread
            ctx.beginPath()
            ctx.ellipse(x, y, width * rnd.uniform(.12, .30) * scale, width * rnd.uniform(.08, .22), math.atan2(dy, dx) + rnd.uniform(-.35, .35), 0, math.tau)
            ctx.fillStyle = color if rnd.random() > .22 else BLUE_DARK
            ctx.globalAlpha = alpha + rnd.random() * .23
            ctx.fill()
    ctx.globalAlpha = 1


def circle(ctx, x: float, y: float, radius: float, seed: int, color: str = ORANGE, dark: str = ORANGE_DARK) -> None:
    rnd = random.Random(seed)
    ctx.save(); ctx.beginPath(); ctx.arc(x, y, radius, 0, math.tau); ctx.clip()
    ctx.fillStyle = color; ctx.globalAlpha = .67; ctx.fillRect(x-radius, y-radius, radius*2, radius*2)
    for scale, count_factor in ((1.0, .055), (.45, .09)):
        for _ in range(max(8, int(radius * radius * count_factor))):
            if rnd.random() < .16:
                continue
            q = rnd.random() * math.tau; rr = math.sqrt(rnd.random()) * radius
            px, py = x + math.cos(q)*rr, y + math.sin(q)*rr
            size = radius * rnd.uniform(.025, .11) * scale
            ctx.beginPath(); ctx.ellipse(px, py, size*1.8, size, rnd.random()*math.pi, 0, math.tau)
            ctx.fillStyle = color if rnd.random() > .25 else dark
            ctx.globalAlpha = rnd.uniform(.14, .42); ctx.fill()
    ctx.restore(); ctx.globalAlpha = 1


def polygon(ctx, points, seed: int) -> None:
    if not points: return
    ctx.beginPath(); ctx.moveTo(*points[0])
    for point in points[1:]: ctx.lineTo(*point)
    ctx.closePath(); ctx.fillStyle = GREEN; ctx.globalAlpha = .66; ctx.fill()
    ctx.strokeStyle = GREEN_DARK; ctx.globalAlpha = .52; ctx.lineWidth = 2; ctx.stroke(); ctx.globalAlpha = 1


def ball(ctx, x: float, y: float, radius: float, seed: int) -> None:
    key = (round(radius), int(seed))
    sprite = _ball_sprites.get(key)
    if sprite is None and document is not None:
        pad = 5; size = math.ceil((radius + pad) * 2)
        sprite = document.createElement("canvas"); sprite.width = size; sprite.height = size
        local = sprite.getContext("2d")
        circle(local, size/2, size/2, radius, seed, "#176bd0", "#0d3d92")
        local.beginPath(); local.arc(size/2-radius*.3, size/2-radius*.34, max(1.2, radius*.2), 0, math.tau)
        local.fillStyle = "rgba(220,240,255,.68)"; local.fill()
        _ball_sprites[key] = sprite
    if sprite is not None:
        ctx.drawImage(sprite, x - sprite.width/2, y - sprite.height/2)
    else:
        circle(ctx, x, y, radius, seed, "#176bd0", "#0d3d92")


def text(ctx, value: str, x: float, y: float, size: float = 12) -> None:
    ctx.fillStyle = TEXT; ctx.font = f"{size}px system-ui, sans-serif"; ctx.fillText(value, x, y)
