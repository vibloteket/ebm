"""Strict tile-local geometry bounds, shared by construction and validation.

Physics shapes are measured from their current transform, never a cached BB.
Balls are not tile-owned geometry and must not be passed to these checks.
"""
from __future__ import annotations

import math

from .ports import TILE_SIZE

GEOMETRY_EPSILON = 1e-7  # Floating-point noise only, not an authoring margin.
MAX_SHAPE_RADIUS = 20.0  # Independent of the tile's strict spatial bounds.


class GeometryBoundsError(ValueError):
    def __init__(self, message, **details):
        super().__init__(message)
        self.details = details


def radius_value(radius, *, maximum=None):
    radius = float(radius)
    if not math.isfinite(radius) or radius < 0 or (maximum is not None and radius > maximum):
        raise ValueError(f"radius must be finite and between 0 and {maximum if maximum is not None else 'infinity'}")
    return radius


def points_bounds(points, radius=0):
    radius = radius_value(radius)
    points = [tuple(map(float, point)) for point in points]
    if not points or any(not math.isfinite(value) for point in points for value in point):
        raise ValueError("geometry coordinates must be finite")
    xs, ys = zip(*points)
    return min(xs) - radius, min(ys) - radius, max(xs) + radius, max(ys) + radius


def check_bounds(bounds, *, label="geometry", **details):
    left, top, right, bottom = bounds
    if not all(math.isfinite(value) for value in bounds):
        raise GeometryBoundsError(f"{label}: geometry bounds must be finite", **details)
    for edge, overflow in (("left", -left), ("top", -top), ("right", right - TILE_SIZE), ("bottom", bottom - TILE_SIZE)):
        if overflow > GEOMETRY_EPSILON:
            raise GeometryBoundsError(
                f"{label}: geometry extends {overflow:.9g} units beyond the {edge} tile edge "
                f"(bounds={tuple(round(value, 9) for value in bounds)}, allowed=0..{TILE_SIZE})",
                **details, edge=edge, overflow=overflow, bounds=list(bounds),
            )


def shape_bounds(shape, origin):
    import pymunk

    if isinstance(shape, pymunk.Circle):
        points = [shape.offset]
    elif isinstance(shape, pymunk.Segment):
        points = [shape.a, shape.b]
    elif isinstance(shape, pymunk.Poly):
        points = shape.get_vertices()
    else:
        raise TypeError(f"unsupported geometry: {type(shape).__name__}")
    ox, oy = origin
    world = [shape.body.local_to_world(point) for point in points]
    # Radius stays circular under rotation. Expanding in body-local space and
    # rotating two diagonal corners does not give the correct world bounds.
    return points_bounds(((point.x - ox, point.y - oy) for point in world), shape.radius)
