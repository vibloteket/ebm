import json
import math

import pymunk
import pytest

from ebm import TileBase
from ebm.editor_runtime import EditorRuntime
from ebm.geometry_bounds import GEOMETRY_EPSILON, GeometryBoundsError, check_bounds, shape_bounds
from ebm.repeat_validation import validate_repeated_flow
from ebm.tile_api import BUILD_MARGIN, TileBuilder, TileResourceRegistry
from ebm.tile_catalog import all_tiles
from ebm.validator import validate_tile_flow


def world(origin=(0, 0)):
    space = pymunk.Space()
    registry = TileResourceRegistry.for_space(space)
    return space, registry, TileBuilder(registry, 1, origin)


@pytest.mark.parametrize("origin", [(0, 0), (400, 200), (-800, -600)])
def test_full_shapes_may_touch_all_edges_but_not_cross(origin):
    space, registry, b = world(origin)
    assert BUILD_MARGIN == 0
    b.static_segment((10, 10), (390, 10), 10)
    b.static_segment((390, 10), (390, 390), 10)
    b.static_segment((390, 390), (10, 390), 10)
    b.static_segment((10, 390), (10, 10), 10)
    b.static_circle((200, 200), 200)
    b.static_polygon(((5, 5), (395, 5), (395, 395), (5, 395)), radius=5)
    b.sensor_box(0, 0, 400, 400)
    b.visual_segment((20, 20), (380, 380), 20)
    registry.validate_geometry()
    assert len(space.shapes) == 7


@pytest.mark.parametrize("construct,edge,overflow", [
    (lambda b: b.static_segment((0, 100), (0, 300), 10), "left", 10),
    (lambda b: b.static_segment((100, 400), (300, 400), 8), "bottom", 8),
    (lambda b: b.static_segment((390, 100), (400, 100), 1), "right", 1),
    (lambda b: b.static_segment((20, 0), (100, 0), 3), "top", 3),
    (lambda b: b.static_circle((5, 20), 10), "left", 5),
    (lambda b: b.static_polygon(((2, 100), (30, 100), (30, 150)), radius=3), "left", 1),
    (lambda b: b.sensor_box(-1, 10, 30, 40), "left", 1),
    (lambda b: b.visual_segment((100, 390), (200, 390), 11), "bottom", 1),
])
def test_build_rejects_overhang_before_registering_any_resource(construct, edge, overflow):
    space, registry, b = world()
    with pytest.raises(GeometryBoundsError) as caught:
        construct(b)
    assert caught.value.details["edge"] == edge
    assert caught.value.details["overflow"] == pytest.approx(overflow)
    assert not space.shapes and not space.bodies
    assert not registry.owned_objects(1)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_coordinates_and_radii_are_rejected(value):
    _, _, b = world()
    for construct in (
        lambda: b.static_segment((value, 100), (100, 100), 2),
        lambda: b.static_circle((100, 100), value),
        lambda: b.visual_segment((20, 20), (100, 100), value),
        lambda: b.static_polygon(((100, 100), (150, 100), (150, 150)), radius=value),
        lambda: b.dynamic_body((value, 100)),
    ):
        with pytest.raises(ValueError):
            construct()


def test_radius_budget_is_independent_of_zero_build_margin():
    _, _, b = world()
    b.static_segment((30, 30), (370, 30), 20)
    b.static_polygon(((30, 40), (80, 40), (80, 80)), radius=20)
    for radius in (-1, 21):
        with pytest.raises(ValueError):
            b.static_segment((30, 30), (370, 30), radius)
    with pytest.raises(ValueError):
        b.visual_segment((30, 30), (370, 30), -1)


def test_rotated_attached_shapes_use_world_geometry_and_circular_radius():
    _, registry, b = world((400, 200))
    body = b.dynamic_body((10, 100), angle=math.pi / 4)
    # At 45 degrees the old two-diagonal-corner check missed circle extent.
    b.circle_shape(body, (0, 0), 10)
    raw_body = registry.resolve(1, body)
    mass, moment, position = raw_body.mass, raw_body.moment, raw_body.position
    with pytest.raises(GeometryBoundsError):
        b.circle_shape(body, (0, 0), 11)
    assert (raw_body.mass, raw_body.moment) == pytest.approx((mass, moment))
    assert raw_body.position == pytest.approx(position)
    segment = b.segment_shape(body, (-5, -5), (20, 20), 2)
    assert shape_bounds(registry.resolve(1, segment), b.origin)[0] == pytest.approx(8)
    # Negative body-local coordinates are valid if world geometry fits.
    centre = b.dynamic_body((200, 200), angle=.7)
    b.polygon_shape(centre, ((-50, -50), (50, -50), (50, 50), (-50, 50)), radius=4)
    registry.validate_geometry()
    with pytest.raises(GeometryBoundsError):
        b.segment_shape(body, (-15, 15), (0, 0), 1)
    with pytest.raises(GeometryBoundsError):
        b.polygon_shape(body, ((-30, 0), (0, -30), (0, 30)), radius=2)


def test_invalid_body_mutations_roll_back_and_visual_mutations_are_atomic():
    _, registry, b = world()
    body = b.dynamic_body((15, 200), angle=math.pi / 2)
    b.segment_shape(body, (-40, 0), (40, 0), 5)
    with pytest.raises(GeometryBoundsError):
        body.set_position((4, 200))
    assert body.position == pytest.approx((15, 200))
    with pytest.raises(GeometryBoundsError):
        body.set_angle(0)
    assert body.angle == pytest.approx(math.pi / 2)
    visual = b.visual_segment((20, 20), (100, 100), 10)
    original = registry.resolve(1, visual)
    with pytest.raises(GeometryBoundsError):
        visual.set_segment_points((5, 20), (100, 100))
    assert registry.resolve(1, visual) == original
    registry.validate_geometry()


def test_numeric_tolerance_is_not_a_build_margin():
    check_bounds((-GEOMETRY_EPSILON / 2, 0, 400, 400))
    with pytest.raises(GeometryBoundsError):
        check_bounds((-GEOMETRY_EPSILON * 2, 0, 400, 400))


class EscapingMechanism(TileBase):
    author = "Tests"

    def build(self, b):
        self.body = b.dynamic_body((389, 200))
        b.circle_shape(self.body, (0, 0), 10)
        self.body.set_velocity((240, 0))


@pytest.mark.parametrize("validator", [validate_tile_flow, validate_repeated_flow])
def test_validators_stop_on_first_physics_step_and_report_geometry_not_ball_failure(validator):
    result = validator(EscapingMechanism, dt=1 / 120)
    assert not result.ok
    error, = result.runtime_errors
    assert error["type"] == "GeometryBoundsError"
    assert error["phase"] == "physics"
    assert error["time"] == pytest.approx(1 / 120)
    assert error["owner"] == 1
    assert error["object_id"] > 0
    assert error["edge"] == "right"
    assert error["overflow"] == pytest.approx(1)
    assert result.lost == 0
    if validator == validate_repeated_flow:
        assert (error["row"], error["col"]) == (0, 0)


class RotatingMechanism(TileBase):
    author = "Tests"

    def build(self, b):
        body = b.dynamic_body((25, 200), angle=math.pi / 2)
        b.segment_shape(body, (-50, 0), (50, 0), 5)
        b.pivot(body, (25, 200))
        body.set_angular_velocity(math.pi * 60)


def test_runtime_rotation_is_measured_after_step_not_using_stale_bb():
    result = validate_tile_flow(RotatingMechanism)
    error, = result.runtime_errors
    assert error["edge"] == "left"
    assert error["phase"] == "physics"
    assert error["overflow"] == pytest.approx(30)


@pytest.mark.parametrize("phase", ["build", "update"])
@pytest.mark.parametrize("validator", [validate_tile_flow, validate_repeated_flow])
def test_post_build_and_update_checks_catch_direct_mutation(phase, validator):
    class Mutated(TileBase):
        author = "Tests"

        def build(self, b):
            self.shape = b.static_circle((200, 200), 10)
            if phase == "build":
                self.update(b, 0)

        def update(self, b, dt):
            # Deliberately bypass the public setter to prove the independent
            # validator catches changed static geometry as well as dynamics.
            raw = b._registry.resolve(b._owner, self.shape)
            raw.body.position = (b.origin[0] + 395, b.origin[1] + 200)

    result = validator(Mutated)
    error, = result.runtime_errors
    assert not result.ok
    assert error["phase"] == phase
    assert error["time"] == 0
    assert error["edge"] == "right"
    assert error["overflow"] == 5


def test_repeat_error_names_actual_tile_not_last_updated_tile():
    class MiddleOnly(EscapingMechanism):
        def build(self, b):
            if b.origin == (400, 600):  # Staggered row 1, column 1.
                super().build(b)

    result = validate_repeated_flow(MiddleOnly)
    error, = result.runtime_errors
    assert (error["owner"], error["row"], error["col"]) == (5, 1, 1)
    assert error["bounds"][2] == pytest.approx(401)


def test_paused_hidden_shapes_are_still_checked_but_balls_are_not():
    space, registry, b = world()
    body = pymunk.Body(1, 1)
    body.position = (-100, 200)
    ball = pymunk.Circle(body, 15)
    space.add(body, ball)
    registry._claim_ball(1, body, ball)
    registry.validate_geometry()
    owned = b.static_circle((200, 200), 10)
    owned.pause()
    registry.resolve(1, owned).body.position = (395, 200)
    with pytest.raises(GeometryBoundsError):
        registry.validate_geometry()


def test_editor_shows_source_line_for_radius_only_overhang():
    source = '''from ebm import TileBase
class BadTile(TileBase):
    author = "Tests"
    def build(self, b):
        b.static_segment((0, 100), (0, 300), radius=10)
'''
    result = json.loads(EditorRuntime().compile(source))
    assert not result["ok"]
    assert result["line"] == 5
    assert "10 units" in result["message"] and "left" in result["message"]


@pytest.mark.parametrize("registration", all_tiles(), ids=lambda r: r.id)
def test_catalog_builds_inside_strict_bounds_at_nonzero_origin(registration):
    _, registry, b = world((-400, 600))
    registration.create().build(b)
    registry.validate_geometry()
