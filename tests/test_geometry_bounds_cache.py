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
    body = b.dynamic_body((15, 200), angle=1.5707963267948966)
    moving = b.segment_shape(body, (-40, 0), (40, 0), 5)
    original = api.transformed_bounds
    measured = []

    def measure(geometry, pose, origin):
        measured.append(pose[0])
        return original(geometry, pose, origin)

    monkeypatch.setattr(api, "transformed_bounds", measure)
    registry.validate_geometry()
    assert len(measured) == 2
    measured.clear()
    registry.validate_geometry(time=.1)
    assert measured == [registry.resolve(1, moving).body.position]
    registry.resolve(1, fixed).body.position = (795, 700)
    with pytest.raises(GeometryBoundsError) as caught:
        registry.validate_geometry(time=.2, phase="update")
    assert caught.value.details["edge"] == "right"
    assert caught.value.details["time"] == .2
    registry.destroy_owner(1)
    assert not registry._checked_static_poses
    assert not registry._static_shape_bodies
    assert not registry._shape_geometries
    assert not registry._body_geometry_radii


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


@pytest.mark.parametrize('angle', [-1.2, 0, .3, 1.5707963267948966])
def test_cached_local_geometry_matches_pymunk_world_transform_with_offset_mass(angle):
    registry = TileResourceRegistry.for_space(pymunk.Space())
    b = TileBuilder(registry, 1, (400, 200))
    body = b.dynamic_body((200, 200), angle=angle)
    shapes = [b.circle_shape(body, (30, -10), 15),
              b.segment_shape(body, (-20, -20), (20, 10), 3),
              b.polygon_shape(body, ((-30, 0), (10, 0), (5, 30)), radius=2)]
    raw = registry.resolve(1, body)
    assert raw.center_of_gravity.length > 0
    for handle in shapes:
        shape = registry.resolve(1, handle)
        _, geometry = registry._shape_geometries[handle.id]
        expected = api.shape_bounds(shape, b.origin)
        actual = api.transformed_bounds(geometry, (raw.position, raw.angle), b.origin)
        assert actual == pytest.approx(expected, abs=1e-10)
    registry.validate_geometry()
