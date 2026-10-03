"""Mirror engine state to the JavaScript scene renderer.

Pure Python (no ``js`` imports) so the exporter is testable natively; the
browser plumbing in ``web_demo.py`` only forwards what this module produces.

Two data flows:

* **Events** (rare): tile add/remove/style, ball add/remove/style. Produced by
  :meth:`SceneExporter.sync` from per-frame diffs of ``engine.active_tiles``
  plus dirty hints pushed through ``TileResourceRegistry.add_scene_listener``.
* **Poses** (every frame): one ``pymunk.batch.get_space_bodies`` call filling
  reused buffers. :meth:`SceneExporter.frame` exposes them as memoryviews that
  the browser layer converts with a single ``to_js`` call each.

Event payloads are nested lists (never dicts) so ``to_js`` yields plain JS
arrays. Shape encodings, tile-local coordinates:

* segment: ``[0, x1, y1, x2, y2, radius, fill, stroke, fg]``
* circle:  ``[1, x, y, radius, fill, stroke, fg]``
* polygon: ``[2, radius, fill, stroke, [x1, y1, ...], fg]``

``fg`` is 1 when the shape is foreground graphics, drawn after balls so it
can occlude them.

Dynamic shapes attached to tile-owned bodies use body-local coordinates and
are grouped under their body id; balls are keyed by body id as well. Colors
are ``[r, g, b, a]`` lists.
"""

from __future__ import annotations

import struct

import pymunk
import pymunk.batch

from .tile_api import DEFAULT_BALL_FILL, DEFAULT_BALL_STROKE, VisualPolygon, VisualSegment

_POSE_FIELDS = (
    pymunk.batch.BodyFields.BODY_ID
    | pymunk.batch.BodyFields.POSITION
    | pymunk.batch.BodyFields.ANGLE
)


def _color(color) -> list[int]:
    return [int(color[0]), int(color[1]), int(color[2]), int(color[3])]


class SceneExporter:
    def __init__(self, engine) -> None:
        self.engine = engine
        self._tiles: dict[int, int] = {}  # owner id -> last exported visual revision
        self._balls: dict[int, tuple] = {}  # body id -> (fill, stroke, paused)
        self._dirty_visuals: set[int] = set()
        self._dirty_dynvisuals: set[int] = set()
        self._dirty_balls: set[int] = set()
        self._buffer = pymunk.batch.Buffer()
        engine.registry.add_scene_listener(self._on_scene_event)

    def _on_scene_event(self, kind: str, ident: int) -> None:
        if kind == "visual":
            self._dirty_visuals.add(ident)
        elif kind == "dynvisual":
            self._dirty_dynvisuals.add(ident)
        else:
            self._dirty_balls.add(ident)

    def sync(self) -> list:
        """Drain scene changes into a flat event list for the JS renderer."""
        events: list = []
        active = {tile.owner_id: tile for tile in self.engine.active_tiles.values()}
        for owner in sorted(set(self._tiles) - set(active)):
            self._tiles.pop(owner, None)
            events.append(["tile_remove", owner])
        dirty_visuals = self._dirty_visuals
        self._dirty_visuals = set()
        refreshed: set[int] = set()
        for owner, tile in sorted(active.items()):
            revision = tile.builder.visual_revision
            if owner not in self._tiles:
                events.append(self._tile_event("tile_add", tile))
                self._tiles[owner] = revision
                refreshed.add(owner)
            elif self._tiles[owner] != revision or owner in dirty_visuals:
                events.append(self._tile_event("tile_style", tile))
                self._tiles[owner] = revision
                refreshed.add(owner)

        # Dynamic visuals move with mechanisms every frame; ship just their
        # current geometry and leave the static layer alone. Tiles refreshed
        # above already carry their current dynamic visuals.
        dirty_dynvisuals = self._dirty_dynvisuals
        self._dirty_dynvisuals = set()
        for owner in sorted(dirty_dynvisuals - refreshed):
            tile = active.get(owner)
            if tile is not None and owner in self._tiles:
                events.append(["tile_dynvisuals", owner, self._dyn_visuals(tile.builder)])

        # Ball add/remove arrive via dirty hints; a count mismatch means a hint
        # was missed (defensive full diff, still rare).
        if self._dirty_balls or len(self.engine.balls) != len(self._balls):
            present = {ball.body.id: ball for ball in self.engine.balls}
            for body_id in sorted(set(self._balls) - set(present)):
                self._balls.pop(body_id, None)
                events.append(["ball_remove", body_id])
            for body_id in sorted(self._dirty_balls | (set(present) - set(self._balls))):
                ball = present.get(body_id)
                if ball is None:
                    continue
                shape = ball.shape
                fill = tuple(getattr(shape, "ebm_fill_color", DEFAULT_BALL_FILL))
                stroke = tuple(getattr(shape, "ebm_stroke_color", DEFAULT_BALL_STROKE))
                paused = bool(self.engine.registry.ball_is_paused(ball.body))
                state = (fill, stroke, paused)
                if body_id not in self._balls:
                    events.append(["ball_add", body_id, float(shape.radius), _color(fill), _color(stroke), paused])
                elif self._balls[body_id] != state:
                    events.append(["ball_style", body_id, _color(fill), _color(stroke), paused])
                self._balls[body_id] = state
            self._dirty_balls.clear()
        return events

    def _dyn_visuals(self, builder) -> list:
        result = []
        for shape, style in builder.visual_items:
            if isinstance(shape, VisualSegment) and shape.dynamic:
                result.append([
                    0, float(shape.a[0]), float(shape.a[1]), float(shape.b[0]), float(shape.b[1]),
                    float(shape.radius), _color(style.fill_color), _color(style.stroke_color),
                    1 if style.foreground else 0,
                ])
        return result

    def _tile_event(self, kind: str, active) -> list:
        builder = active.builder
        ox, oy = builder.origin
        statics: list = []
        dyn_visuals: list = []
        dyn_bodies: dict[int, list] = {}
        for shape, style in builder.visual_items:
            fill = _color(style.fill_color)
            stroke = _color(style.stroke_color)
            fg = 1 if style.foreground else 0
            if isinstance(shape, VisualPolygon):
                points: list[float] = []
                for px, py in shape.points:
                    points += [float(px), float(py)]
                statics.append([2, float(shape.radius), fill, stroke, points, fg])
                continue
            if isinstance(shape, VisualSegment):
                entry = [0, float(shape.a[0]), float(shape.a[1]), float(shape.b[0]), float(shape.b[1]), float(shape.radius), fill, stroke, fg]
                (dyn_visuals if shape.dynamic else statics).append(entry)
                continue
            body = getattr(shape, "body", None)
            if body is None or getattr(shape, "ebm_hidden", False):
                continue
            if body.body_type == pymunk.Body.STATIC:
                entry = self._static_entry(shape, body, ox, oy, fill, stroke, fg)
                if entry is not None:
                    statics.append(entry)
                continue
            entry = self._local_entry(shape, fill, stroke, fg)
            if entry is not None:
                dyn_bodies.setdefault(body.id, []).append(entry)
        return [
            kind,
            active.owner_id,
            float(ox),
            float(oy),
            statics,
            dyn_visuals,
            [[body_id, shapes] for body_id, shapes in dyn_bodies.items()],
        ]

    @staticmethod
    def _static_entry(shape, body, ox: float, oy: float, fill, stroke, fg):
        name = type(shape).__name__
        if name == "Segment":
            a = body.local_to_world(shape.a)
            b = body.local_to_world(shape.b)
            return [0, float(a.x) - ox, float(a.y) - oy, float(b.x) - ox, float(b.y) - oy, float(shape.radius), fill, stroke, fg]
        if name == "Circle":
            p = body.local_to_world(shape.offset)
            return [1, float(p.x) - ox, float(p.y) - oy, float(shape.radius), fill, stroke, fg]
        if name == "Poly":
            points: list[float] = []
            for vertex in shape.get_vertices():
                w = body.local_to_world(vertex)
                points += [float(w.x) - ox, float(w.y) - oy]
            return [2, float(shape.radius), fill, stroke, points, fg]
        return None

    @staticmethod
    def _local_entry(shape, fill, stroke, fg):
        name = type(shape).__name__
        if name == "Segment":
            return [0, float(shape.a[0]), float(shape.a[1]), float(shape.b[0]), float(shape.b[1]), float(shape.radius), fill, stroke, fg]
        if name == "Circle":
            return [1, float(shape.offset[0]), float(shape.offset[1]), float(shape.radius), fill, stroke, fg]
        if name == "Poly":
            points: list[float] = []
            for vertex in shape.get_vertices():
                points += [float(vertex[0]), float(vertex[1])]
            return [2, float(shape.radius), fill, stroke, points, fg]
        return None

    def frame(self):
        """Fill the pose buffers; return (uint32 ids view, float64 poses view, id stride).

        Body ids are pointer-sized: one uint32 per body on wasm32, two
        (little-endian) on 64-bit hosts. ``id_stride`` tells the JS side how
        many uint32 lanes make one id; combining them yields the same Number
        as the plain-int ids in events (pointers stay below 2**53).

        Layout: body ``i`` uses ``ids[i*id_stride .. i*id_stride+id_stride]``
        and ``floats[3*i] = x``, ``floats[3*i+1] = y``, ``floats[3*i+2] = angle``.
        The views alias reused C buffers; the caller must hand them to JS
        (which copies) before the next ``frame`` call.
        """
        self._buffer.clear()
        pymunk.batch.get_space_bodies(self.engine.space, _POSE_FIELDS, self._buffer)
        ids = memoryview(self._buffer.int_buf()).cast("I")
        floats = memoryview(self._buffer.float_buf()).cast("d")
        return ids, floats, struct.calcsize("P") // 4
