import pymunk
import pytest

from ebm.geometry_bounds import GeometryBoundsError
from ebm.tile_api import TileBuilder, TileResourceRegistry, VisualSegment
import ebm.tile_api as api


def test_static_cache_skips_unchanged_geometry_but_not_dynamic_shapes_or_static_transforms(monkeypatch):
    space = pymunk.Space()
    registry = TileResourceRegistry.for_space(space)
    b = TileBuilder(registry, 1, (400, 600))
    fixed = b.static_circle((100, 100), 10)
    body = b.dynamic_body((200, 200))
    moving = b.circle_shape(body, (0, 0), 10)
    original = api.shape_bounds
    measured = []

    def measure(shape, origin):
        measured.append(shape)
        return original(shape, origin)

    monkeypatch.setattr(api, "shape_bounds", measure)
    registry.validate_geometry()
    assert len(measured) == 2
    measured.clear()
    registry.validate_geometry(time=.1)
    assert measured == [registry.resolve(1, moving)]
    registry.resolve(1, fixed).body.position = (795, 700)
    with pytest.raises(GeometryBoundsError) as caught:
        registry.validate_geometry(time=.2, phase="update")
    assert caught.value.details["edge"] == "right"
    assert caught.value.details["time"] == .2
    registry.destroy_owner(1)
    assert not registry._checked_static_poses
    assert not registry._static_shape_bodies


def test_visual_cache_rechecks_replacement_and_cleanup_releases_it():
    registry = TileResourceRegistry.for_space(pymunk.Space())
    b = TileBuilder(registry, 1, (0, 0))
    visual = b.visual_segment((20, 20), (100, 100), 10)
    registry.validate_geometry()
    visual.set_segment_points((30, 30), (200, 200))
    registry.validate_geometry()
    assert registry._checked_visuals[visual.id].a == (30, 30)
    # Independent runtime measurement catches a replacement that bypasses
    # the public API's immediate endpoint check.
    registry._objects[visual.id] = VisualSegment((0, 0), (100, 100), 10)
    with pytest.raises(GeometryBoundsError):
        registry.validate_geometry()
    registry.destroy_owner(1)
    assert not registry._checked_visuals


def test_nonfinite_static_transform_is_reported_with_owner_and_time_after_cache_hit():
    registry = TileResourceRegistry.for_space(pymunk.Space())
    b = TileBuilder(registry, 5, (400, 600))
    shape = b.static_circle((200, 200), 10)
    registry.validate_geometry()
    registry.resolve(5, shape).body.position = (float("nan"), 800)
    with pytest.raises(GeometryBoundsError) as caught:
        registry.validate_geometry(time=2, phase="update")
    assert caught.value.details == {"owner": 5, "object_id": shape.id, "time": 2, "phase": "update"}
    assert "finite" in str(caught.value)
