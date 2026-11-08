"""Owned, tile-local visual geometry getters/setters and scene invalidation."""
from dataclasses import FrozenInstanceError

import pymunk
import pytest

from ebm.tile_api import VisualHandle
from test_animated_visuals import make, world


def read(handle, kind):
    if kind == "circle":
        return handle.center
    if kind == "segment":
        return handle.segment_points
    return handle.points


def move(handle, kind, shift):
    if kind == "circle":
        handle.set_center(handle.center + shift)
    elif kind == "segment":
        a, b = handle.segment_points
        handle.set_segment_points(a + shift, b + shift)
    else:
        handle.set_points(tuple(point + shift for point in handle.points))


@pytest.mark.parametrize("kind", ["circle", "segment", "polygon", "box"])
@pytest.mark.parametrize("dynamic", [False, True])
@pytest.mark.parametrize("foreground", [False, True])
def test_geometry_roundtrip_local_snapshot_and_scene_updates(kind, dynamic, foreground):
    registry, builder, exporter = world()  # origin=(800, 400), not (0, 0)
    handle = make(builder, kind, dynamic=dynamic, foreground=foreground)
    old = read(handle, kind)
    expected = (100, 120) if kind == "circle" else ((50, 50), (100, 100)) if kind == "segment" else ((50, 50), (100, 50), (100, 100)) if kind == "polygon" else ((50, 50), (100, 50), (100, 100), (50, 100))
    assert old == expected
    values = (old,) if kind == "circle" else old
    assert all(isinstance(value, pymunk.Vec2d) for value in values)
    original = registry.resolve(1, handle)
    style = builder.visual_items[0][1]
    exporter.sync()
    revision = builder.visual_revision
    shift = pymunk.Vec2d(10, 20)
    move(handle, kind, shift)
    new = read(handle, kind)
    assert new == (old + shift if kind == "circle" else tuple(point + shift for point in old))
    assert old == expected  # reads don't alias mutable internal geometry
    replacement = registry.resolve(1, handle)
    assert replacement.radius == original.radius
    assert replacement.dynamic == original.dynamic
    assert builder.visual_items[0][1] is style
    registry.validate_geometry(1)
    event, = exporter.sync()
    assert event[0] == ("tile_dynvisuals" if dynamic else "tile_style")
    assert (builder.visual_revision == revision) == dynamic
    entry, = event[2] if dynamic else event[4]
    if kind == "circle":
        assert entry[1:3] == list(new)
    elif kind == "segment":
        assert entry[1:5] == [value for point in new for value in point]
    else:
        assert entry[4] == [value for point in new for value in point]
    assert entry[-1] == int(foreground)
    move(handle, kind, pymunk.Vec2d(1, 0))
    exporter.sync()
    builder.remove(handle)
    with pytest.raises(PermissionError):
        read(handle, kind)


@pytest.mark.parametrize("kind", ["circle", "segment", "polygon", "box"])
def test_paused_geometry_can_be_edited_and_resumed(kind):
    registry, builder, exporter = world()
    handle = make(builder, kind, dynamic=True)
    handle.pause()
    exporter.sync()
    move(handle, kind, pymunk.Vec2d(10, 20))
    registry.validate_geometry(1)
    assert not builder.visual_items
    handle.resume()
    event, = exporter.sync()
    assert event[0] == "tile_dynvisuals" and len(event[2]) == 1


@pytest.mark.parametrize("kind", ["circle", "segment", "polygon"])
def test_invalid_edits_are_atomic_and_emit_no_scene_changes(kind):
    registry, builder, exporter = world()
    handle = make(builder, kind, dynamic=True)
    exporter.sync()
    before = registry.resolve(1, handle)
    bad_points = [(float("nan"), 20), (float("inf"), 20), (-100, 100), (500, 100), (10,), (10, 20, 30)]
    for point in bad_points:
        with pytest.raises((ValueError, TypeError)):
            if kind == "circle":
                handle.set_center(point)
            elif kind == "segment":
                handle.set_segment_points(point, (200, 200))
            else:
                handle.set_points((point, (200, 100), (200, 200)))
        assert registry.resolve(1, handle) is before
        assert exporter.sync() == []
    if kind == "polygon":
        for points in ((), ((100, 100), (200, 100))):
            with pytest.raises(ValueError, match="at least three"):
                handle.set_points(points)
            assert registry.resolve(1, handle) is before


def test_getters_and_setters_check_geometry_type_ownership_and_dead_handles():
    registry, builder, _ = world()
    for kind in ("circle", "segment", "polygon"):
        handle = make(builder, kind)
        for other in set(("circle", "segment", "polygon")) - {kind}:
            with pytest.raises(TypeError):
                read(handle, other)
            with pytest.raises(TypeError):
                if other == "circle":
                    handle.set_center((100, 100))
                elif other == "segment":
                    handle.set_segment_points((50, 50), (100, 100))
                else:
                    handle.set_points(((50, 50), (100, 50), (100, 100)))
        forged = VisualHandle(handle.id, 2, registry)
        with pytest.raises(PermissionError):
            read(forged, kind)
        with pytest.raises(PermissionError):
            if kind == "circle":
                forged.set_center((100, 100))
            elif kind == "segment":
                forged.set_segment_points((50, 50), (100, 100))
            else:
                forged.set_points(((50, 50), (100, 50), (100, 100)))
        builder.remove(handle)
        with pytest.raises(PermissionError):
            move(handle, kind, pymunk.Vec2d(1, 0))


def test_geometry_getters_are_read_only_and_polygon_inputs_are_copied():
    _, builder, _ = world()
    points = [[50, 50], [100, 50], [100, 100]]
    polygon = make(builder, "polygon")
    polygon.set_points(points)
    points[0][0] = 999
    assert polygon.points[0] == (50, 50)
    for handle, name in ((make(builder, "circle"), "center"), (make(builder, "segment"), "segment_points"), (polygon, "points")):
        with pytest.raises((AttributeError, FrozenInstanceError)):
            setattr(handle, name, None)


def test_new_setters_noop_without_scene_updates_and_include_radius_in_bounds():
    registry, builder, exporter = world()
    circle = builder.visual_circle((100, 100), 10, dynamic=True)
    polygon = builder.visual_polygon(((50, 50), (100, 50), (100, 100)), radius=5, dynamic=True)
    exporter.sync()
    circle.set_center(circle.center)
    polygon.set_points(polygon.points)
    assert exporter.sync() == []
    for handle, change in ((circle, lambda: circle.set_center((5, 100))), (polygon, lambda: polygon.set_points(((1, 50), (100, 50), (100, 100))))):
        before = registry.resolve(1, handle)
        with pytest.raises(ValueError):
            change()
        assert registry.resolve(1, handle) is before
        assert exporter.sync() == []
