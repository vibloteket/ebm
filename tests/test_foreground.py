"""Foreground rendering flag: API storage, validation, and scene export."""
from types import SimpleNamespace

import pymunk
import pytest

from ebm.scene_export import SceneExporter
from ebm.tile_api import TileBuilder, TileResourceRegistry, VisualPolygon, VisualSegment


def _world():
    space = pymunk.Space()
    registry = TileResourceRegistry.for_space(space)
    builder = TileBuilder(registry, 1, (0, 0))
    return space, registry, builder


def test_foreground_defaults_false_and_is_stored_on_all_resource_kinds():
    _space, registry, b = _world()
    plain = b.static_segment((10, 10), (100, 10), 3)
    front_rail = b.static_segment((10, 20), (100, 20), 3, foreground=True)
    front_circle = b.static_circle((200, 100), 20, foreground=True)
    front_poly = b.static_polygon(((10, 300), (100, 300), (60, 350)), foreground=True)
    body = b.dynamic_body((200, 200))
    plain_shape = b.circle_shape(body, (0, 0), 10)
    front_shape = b.segment_shape(body, (-10, 20), (10, 20), 2, foreground=True)
    plain_visual = b.visual_segment((10, 380), (100, 380), 3)
    front_visual = b.visual_segment((10, 390), (100, 390), 3, foreground=True)
    front_plate = b.visual_polygon(((150, 300), (250, 300), (250, 390), (150, 390)),
                                   foreground=True)

    assert registry._styles[plain.id].foreground is False
    assert registry._styles[plain_shape.id].foreground is False
    assert registry._styles[plain_visual.id].foreground is False
    for handle in (front_rail, front_circle, front_poly, front_shape,
                   front_visual, front_plate):
        assert registry._styles[handle.id].foreground is True


def test_foreground_rejects_non_bool():
    _space, _registry, b = _world()
    with pytest.raises(ValueError, match="foreground"):
        b.static_segment((10, 10), (100, 10), 3, foreground=1)
    with pytest.raises(ValueError, match="foreground"):
        b.visual_segment((10, 10), (100, 10), 3, foreground="yes")
    with pytest.raises(ValueError, match="foreground"):
        b.visual_polygon(((10, 10), (100, 10), (60, 60)), foreground=0)


def test_visual_polygon_is_bounded_and_non_physical():
    space, registry, b = _world()
    with pytest.raises(Exception, match="bounds"):
        b.visual_polygon(((10, 10), (500, 10), (60, 60)))
    plate = b.visual_polygon(((10, 10), (100, 10), (100, 100)),
                             fill_color=(1, 2, 3, 255), foreground=True)
    # Visuals never enter the physics space.
    assert len(list(space.shapes)) == 0
    obj = registry.resolve(1, plate)
    assert isinstance(obj, VisualPolygon)
    assert obj.points == ((10.0, 10.0), (100.0, 10.0), (100.0, 100.0))
    # Bounds validation accepts the plate and its paused state alike.
    registry.validate_geometry(time=0, phase="test")


def test_scene_export_carries_the_foreground_flag():
    def build(b):
        b.static_segment((10, 10), (100, 10), 3)  # bg segment
        b.static_segment((10, 20), (100, 20), 3, foreground=True)  # fg segment
        b.static_circle((200, 100), 20, foreground=True)  # fg circle
        b.visual_polygon(((150, 300), (250, 300), (250, 390)),  # fg plate
                         fill_color=(9, 9, 9, 255), foreground=True)
        body = b.dynamic_body((200, 200))
        b.circle_shape(body, (0, 0), 10, foreground=True)  # fg body shape
        b.visual_segment((10, 380), (100, 380), 3, dynamic=True, foreground=True)

    space = pymunk.Space()
    registry = TileResourceRegistry.for_space(space)
    builder = TileBuilder(registry, 1, (0, 0))
    build(builder)
    active = {(0, 0): SimpleNamespace(builder=builder, owner_id=1, tile=object())}
    engine = SimpleNamespace(space=space, registry=registry, active_tiles=active, balls=[])
    exporter = SceneExporter(engine)

    adds = [event for event in exporter.sync() if event[0] == "tile_add"]
    assert len(adds) == 1
    _kind, _owner, _ox, _oy, statics, dyn_visuals, dyn_bodies = adds[0]

    segments = [s for s in statics if s[0] == 0]
    assert [s[8] for s in segments] == [0, 1]
    circles = [s for s in statics if s[0] == 1]
    assert [c[6] for c in circles] == [1]
    polys = [s for s in statics if s[0] == 2]
    assert len(polys) == 1 and polys[0][5] == 1
    assert polys[0][4] == [150.0, 300.0, 250.0, 300.0, 250.0, 390.0]

    assert len(dyn_visuals) == 1 and dyn_visuals[0][8] == 1
    assert len(dyn_bodies) == 1
    _body_id, shapes = dyn_bodies[0]
    assert len(shapes) == 1 and shapes[0][6] == 1
