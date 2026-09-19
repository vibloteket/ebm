import pymunk
import pytest

import ebm.tile_api as api
from ebm.geometry_bounds import GeometryBoundsError


def setup():
    registry = api.TileResourceRegistry.for_space(pymunk.Space())
    b = api.TileBuilder(registry, 1, (400, 200))
    body = b.dynamic_body((200, 200))
    b.circle_shape(body, (0, 0), 10)
    return registry, b, body


def test_safe_body_circle_skips_exact_shapes_but_near_edge_uses_exact_bounds(monkeypatch):
    registry, b, body = setup()
    calls = []
    original = api.transformed_bounds

    def measure(*args):
        calls.append(args)
        return original(*args)

    monkeypatch.setattr(api, 'transformed_bounds', measure)
    registry.validate_geometry()
    assert not calls
    raw = registry.resolve(1, body)
    raw.position = (795, 400)
    with pytest.raises(GeometryBoundsError, match='right'):
        registry.validate_geometry()
    assert len(calls) == 1


def test_new_shapes_expand_the_conservative_body_circle():
    registry, b, body = setup()
    raw = registry.resolve(1, body)
    b.segment_shape(body, (0, 0), (195, 0), 5)
    assert registry._body_geometry_radii[raw] == pytest.approx(200)
    registry.validate_geometry()
    raw.position = (601, 400)
    with pytest.raises(GeometryBoundsError, match='right'):
        registry.validate_geometry()


@pytest.mark.parametrize('angle', [float('nan'), float('inf')])
def test_interior_guard_does_not_accept_nonfinite_rotation(angle):
    registry, b, body = setup()
    registry.resolve(1, body).angle = angle
    with pytest.raises(GeometryBoundsError):
        registry.validate_geometry()
