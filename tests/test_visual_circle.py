"""Non-physical circles share ownership, styling and rendering with other visuals."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace

import pymunk
import pytest

from ebm.geometry_bounds import GeometryBoundsError
from ebm.ports import TILE_SIZE
from ebm.scene_export import SceneExporter
from ebm.tile_api import (
    DEFAULT_CIRCLE_FILL, DEFAULT_CIRCLE_STROKE, TileBuilder,
    TileResourceRegistry, VisualCircle, VisualHandle, VisualPolygon, VisualSegment,
)


def builder():
    space = pymunk.Space()
    registry = TileResourceRegistry.for_space(space)
    owner = 1
    return space, registry, owner, TileBuilder(registry, owner, (800, 400))


def test_circle_is_local_nonphysical_and_owned():
    space, registry, owner, ctx = builder()
    circle = ctx.visual_circle((100, 120), 30)
    assert isinstance(circle, VisualHandle)
    assert registry.owned_visuals(owner) == [VisualCircle((100, 120), 30)]
    shape, style = ctx.visual_items[0]
    assert style.fill_color == DEFAULT_CIRCLE_FILL
    assert style.stroke_color == DEFAULT_CIRCLE_STROKE
    assert not style.foreground
    assert not space.shapes and not space.bodies
    registry.validate_geometry(owner)
    ctx.visual_circle((0, 0), 0)
    ctx.visual_circle((TILE_SIZE / 2, TILE_SIZE / 2), TILE_SIZE / 2)
    registry.validate_geometry(owner)
    registry.destroy_owner(owner)
    assert not ctx.visual_objects
    with pytest.raises(PermissionError):
        circle.set_fill_color(None)


@pytest.mark.parametrize("center,radius", [
    ((9, 20), 10), ((20, 9), 10),
    ((TILE_SIZE - 9, 20), 10), ((20, TILE_SIZE - 9), 10),
])
def test_circle_rejects_overhang_without_registering(center, radius):
    _, _, _, ctx = builder()
    with pytest.raises(GeometryBoundsError):
        ctx.visual_circle(center, radius)
    assert not ctx.visual_objects


@pytest.mark.parametrize("center,radius", [
    ((math.nan, 20), 10), ((20, math.inf), 10),
    ((20, 20), -1), ((20, 20), math.nan), ((20, 20), math.inf),
])
def test_circle_rejects_invalid_geometry(center, radius):
    _, _, _, ctx = builder()
    with pytest.raises(ValueError):
        ctx.visual_circle(center, radius)
    assert not ctx.visual_objects


def test_circle_style_validation_mutation_and_removal():
    _, registry, owner, ctx = builder()
    with pytest.raises(ValueError, match="foreground"):
        ctx.visual_circle((40, 40), 10, foreground=1)
    with pytest.raises(ValueError):
        ctx.visual_circle((40, 40), 10, fill_color=(256, 0, 0, 255))
    assert not ctx.visual_objects
    circle = ctx.visual_circle((40, 40), 10, fill_color=None, stroke_color=None, foreground=True)
    _, style = ctx.visual_items[0]
    assert style.fill_color == style.stroke_color == (0, 0, 0, 0)
    assert style.foreground
    revision = ctx.visual_revision
    circle.set_fill_color((1, 2, 3, 255))
    assert ctx.visual_revision > revision
    assert style.fill_color == (1, 2, 3, 255)
    registry.validate_geometry(owner)
    circle.pause()
    assert not ctx.visual_items
    registry.validate_geometry(owner)  # Paused visuals remain bounds-checked.
    circle.resume()
    assert len(ctx.visual_items) == 1
    ctx.remove(circle)
    assert not ctx.visual_objects
    with pytest.raises(PermissionError):
        circle.set_stroke_color(None)


def test_circle_scene_export_and_refresh():
    space, registry, owner, ctx = builder()
    active = SimpleNamespace(builder=ctx, owner_id=owner)
    engine = SimpleNamespace(space=space, registry=registry, active_tiles={(0, 0): active}, balls=[])
    exporter = SceneExporter(engine)
    exporter.sync()
    handle = active.builder.visual_circle((123, 234), 31, fill_color=(1, 2, 3, 255), stroke_color=None, foreground=True)
    event = next(e for e in exporter.sync() if e[0] == "tile_style")
    expected = [1, 123.0, 234.0, 31.0, [1, 2, 3, 255], [0, 0, 0, 0], 1]
    assert expected in event[4]
    handle.set_fill_color(None)
    event = next(e for e in exporter.sync() if e[0] == "tile_style")
    expected[4] = [0, 0, 0, 0]
    assert expected in event[4]
    active.builder.remove(handle)
    event = next(e for e in exporter.sync() if e[0] == "tile_style")
    assert expected not in event[4]


def test_circle_editor_draws_local_center_and_correct_layer():
    # Extract the pure drawing helper without importing the browser-only js module.
    tree = ast.parse(Path("ebm/editor_preview.py").read_text())
    helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_draw_tile_items")
    namespace = dict(math=math, VisualCircle=VisualCircle, VisualSegment=VisualSegment,
                     VisualPolygon=VisualPolygon, _canvas_color=lambda color: color)
    exec(compile(ast.Module(body=[helper], type_ignores=[]), "editor_draw", "exec"), namespace)
    _, _, _, ctx = builder()
    ctx.visual_circle((40, 50), 10, fill_color=None, foreground=True)
    calls = []
    canvas = SimpleNamespace(beginPath=lambda: None, arc=lambda *args: calls.append(args),
                             fill=lambda: calls.append("fill"), stroke=lambda: calls.append("stroke"))
    draw = namespace["_draw_tile_items"]
    draw(canvas, ctx, lambda x: x * 2, lambda y: y * 2, 2, foreground=False)
    assert calls == []
    draw(canvas, ctx, lambda x: x * 2, lambda y: y * 2, 2, foreground=True)
    assert calls == [(1680, 900, 20, 0, math.tau), "stroke"]
