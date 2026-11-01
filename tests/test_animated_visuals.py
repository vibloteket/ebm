"""Dynamic primitives update without invalidating the static scene cache."""
from types import SimpleNamespace

import pymunk
import pytest

from ebm.scene_export import SceneExporter
from ebm.tile_api import TileBuilder, TileResourceRegistry, VisualCircle


def world():
    space = pymunk.Space()
    registry = TileResourceRegistry.for_space(space)
    builder = TileBuilder(registry, 1, (800, 400))
    active = {(0, 0): SimpleNamespace(owner_id=1, builder=builder)}
    engine = SimpleNamespace(space=space, registry=registry, active_tiles=active, balls=[])
    exporter = SceneExporter(engine)
    exporter.sync()
    return registry, builder, exporter


def make(builder, kind, **kwargs):
    if kind == "circle":
        return builder.visual_circle((100, 120), 10, **kwargs)
    if kind == "segment":
        return builder.visual_segment((50, 50), (100, 100), 2, **kwargs)
    if kind == "polygon":
        return builder.visual_polygon(((50, 50), (100, 50), (100, 100)), **kwargs)
    return builder.visual_box(50, 50, 100, 100, **kwargs)


@pytest.mark.parametrize("kind,tag", [("segment", 0), ("circle", 1), ("polygon", 2), ("box", 2)])
@pytest.mark.parametrize("foreground", [False, True])
def test_dynamic_primitive_lifecycle(kind, tag, foreground):
    registry, builder, exporter = world()
    revision = builder.visual_revision
    handle = make(builder, kind, dynamic=True, foreground=foreground)

    def only_dynamic(count):
        events = exporter.sync()
        assert len(events) == 1 and events[0][:2] == ["tile_dynvisuals", 1]
        entries = events[0][2]
        assert len(entries) == count
        if entries:
            assert entries[0][0] == tag
            assert entries[0][-1] == int(foreground)
        assert builder.visual_revision == revision
        return entries

    only_dynamic(1)
    handle.set_fill_color(None)
    only_dynamic(1)
    handle.set_stroke_color((1, 2, 3, 255))
    only_dynamic(1)
    handle.pause()
    only_dynamic(0)
    registry.validate_geometry(1)
    handle.resume(delay=.1)
    assert exporter.sync() == []
    registry.advance(.1)
    only_dynamic(1)
    builder.remove(handle)
    only_dynamic(0)


@pytest.mark.parametrize("kind", ["segment", "circle", "polygon", "box"])
def test_dynamic_flag_is_boolean_and_defaults_static(kind):
    _, builder, exporter = world()
    with pytest.raises(ValueError, match="dynamic"):
        make(builder, kind, dynamic=1)
    assert not builder.visual_items
    handle = make(builder, kind)
    assert not builder.visual_items[0][0].dynamic
    event, = exporter.sync()
    assert event[0] == "tile_style" and len(event[4]) == 1 and event[5] == []
    handle.set_fill_color(None)
    assert exporter.sync()[0][0] == "tile_style"


@pytest.mark.parametrize("dynamic", [False, True])
def test_resize_preserves_handle_and_style_and_batches_events(dynamic):
    registry, builder, exporter = world()
    handle = builder.visual_circle((100, 120), 1, dynamic=dynamic, foreground=True)
    exporter.sync()
    revision = builder.visual_revision
    style = builder.visual_items[0][1]
    for radius in (0, 2, 8, 15):
        handle.set_radius(radius)
    assert registry.resolve(1, handle) == VisualCircle((100, 120), 15, dynamic)
    assert builder.visual_items[0][1] is style and style.foreground
    registry.validate_geometry(1)
    event, = exporter.sync()
    if dynamic:
        assert event == ["tile_dynvisuals", 1, [[1, 100., 120., 15., list(style.fill_color), list(style.stroke_color), 1]]]
        assert builder.visual_revision == revision
    else:
        assert event[0] == "tile_style" and event[4][0][3] == 15
        assert builder.visual_revision > revision
    handle.set_radius(15)
    assert exporter.sync() == []


@pytest.mark.parametrize("radius", [-1, float("nan"), float("inf"), 101])
def test_bad_resize_is_atomic(radius):
    registry, builder, exporter = world()
    handle = builder.visual_circle((100, 120), 10, dynamic=True)
    exporter.sync()
    before = registry.resolve(1, handle)
    with pytest.raises(ValueError):
        handle.set_radius(radius)
    assert registry.resolve(1, handle) is before
    assert exporter.sync() == []


def test_resize_checks_resource_type_ownership_and_paused_geometry():
    registry, builder, exporter = world()
    segment = make(builder, "segment")
    with pytest.raises(TypeError, match="visual circle"):
        segment.set_radius(5)
    handle = make(builder, "circle", dynamic=True)
    with pytest.raises(PermissionError):
        registry.set_visual_circle_radius(2, handle, 5)
    handle.pause()
    handle.set_radius(20)
    registry.validate_geometry(1)
    assert registry.resolve(1, handle).radius == 20
    handle.resume()
    exporter.sync()
    registry.destroy_owner(1)
    with pytest.raises(PermissionError):
        handle.set_radius(5)


def test_initial_export_and_mixed_dynamic_static_refresh():
    _, builder, exporter = world()
    make(builder, "circle", dynamic=True)
    make(builder, "polygon", dynamic=True)
    make(builder, "box", dynamic=True, foreground=True)
    make(builder, "segment", dynamic=True)
    make(builder, "circle")
    event, = exporter.sync()
    assert event[0] == "tile_style"
    assert [s[0] for s in event[4]] == [1]
    assert [s[0] for s in event[5]] == [1, 2, 2, 0]
    # A new exporter receives the same shapes on tile_add, not just on updates.
    fresh = SceneExporter(exporter.engine)
    initial, = fresh.sync()
    assert initial[0] == "tile_add" and initial[4:] == event[4:]
