import math

import pymunk
import pytest

from ebm import Tween, ease
from ebm.geometry_bounds import GeometryBoundsError
from ebm.scene_export import SceneExporter
from ebm.tile_api import TileBuilder, TileResourceRegistry
from types import SimpleNamespace


def test_callback_timing_and_exact_completion():
    values = []
    tween = Tween(1, 15, duration=2, apply=values.append)
    assert tween.value == 1 and not tween.done and values == []
    assert tween.update(.5) == 4.5
    assert values == [4.5] and not tween.done
    assert tween.update(1.5) == 15
    assert tween.done and values == [4.5, 15]
    assert tween.update(100) == 15
    assert tween.update(0) == 15
    assert values == [4.5, 15]


def test_done_becomes_true_only_after_callback_succeeds():
    observed = []
    tween = Tween(1, 15, duration=2, apply=lambda value: observed.append((value, tween.done)))
    tween.update(2)
    assert observed == [(15, False)] and tween.done


@pytest.mark.parametrize("steps", [[2], [.25] * 8, [1 / 60] * 120, [.1] * 20, [3]])
def test_partition_independent_completion(steps):
    tween = Tween(1, 15, duration=2, easing=ease.in_out_sine)
    for dt in steps:
        tween.update(dt)
    assert tween.done and tween.value == 15


def test_value_only_descending_and_equal_endpoints():
    tween = Tween(10, -10, duration=2)
    assert tween.update(.5) == 5
    assert tween.update(.5) == 0
    assert tween.update(1) == -10 and tween.done
    same = Tween(3, 3, duration=2)
    assert same.update(1) == 3 and not same.done
    assert same.update(1) == 3 and same.done


def test_zero_duration_and_zero_delta():
    values = []
    instant = Tween(1, 15, duration=0, apply=values.append)
    assert not instant.done and values == []
    assert instant.update(0) == 15 and instant.done
    assert values == [15]
    tween = Tween(1, 15, duration=2, apply=values.append)
    assert tween.update(0) == 1 and not tween.done
    assert values == [15, 1]


def test_custom_easing_and_overshoot_without_clamping():
    values = []
    tween = Tween(0, 10, duration=1, apply=values.append, easing=lambda t: t * 3)
    assert tween.update(.5) == 15
    assert tween.update(.5) == 10 and tween.done
    assert values == [15, 10]
    # Custom easing cannot move either exact endpoint.
    tween = Tween(1, 15, duration=1, easing=lambda t: 42)
    assert tween.update(0) == 1
    assert tween.update(1) == 15


@pytest.mark.parametrize("field", ["start", "end", "duration"])
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_constructor_values(field, value):
    args = dict(start=1, end=15, duration=2)
    args[field] = value
    with pytest.raises(ValueError, match="finite"):
        Tween(**args)


def test_invalid_duration_and_callables():
    with pytest.raises(ValueError, match="nonnegative"):
        Tween(1, 15, duration=-1)
    with pytest.raises(TypeError, match="apply"):
        Tween(1, 15, duration=2, apply=3)
    with pytest.raises(TypeError, match="easing"):
        Tween(1, 15, duration=2, easing=None)


@pytest.mark.parametrize("dt", [-1, math.nan, math.inf, -math.inf])
def test_invalid_dt_does_not_advance_even_after_completion(dt):
    values = []
    tween = Tween(1, 15, duration=2, apply=values.append)
    with pytest.raises(ValueError):
        tween.update(dt)
    assert tween.value == 1 and not tween.done and values == []
    tween.update(2)
    with pytest.raises(ValueError):
        tween.update(dt)
    assert tween.done and values == [15]


@pytest.mark.parametrize("result", [math.nan, math.inf, -math.inf])
def test_nonfinite_easing_result_does_not_apply_or_advance(result):
    values = []
    tween = Tween(1, 15, duration=2, apply=values.append, easing=lambda t: result)
    with pytest.raises(ValueError, match="easing result"):
        tween.update(1)
    assert tween.value == 1 and not tween.done and values == []


def test_easing_and_callback_exceptions_propagate_without_advancing():
    def fail(value):
        raise RuntimeError("test failure")
    for options in ({"apply": fail}, {"easing": fail}):
        tween = Tween(1, 15, duration=2, **options)
        with pytest.raises(RuntimeError, match="test failure"):
            tween.update(1)
        assert tween.value == 1 and not tween.done
    # A failed final callback leaves completion pending too.
    tween = Tween(1, 15, duration=2, apply=fail)
    with pytest.raises(RuntimeError):
        tween.update(2)
    assert not tween.done and tween.value == 1


def test_large_finite_endpoints_and_overflow_guard():
    tween = Tween(-1e308, 1e308, duration=2)
    assert tween.update(1) == 0
    assert tween.update(1) == 1e308
    tween = Tween(1e308, -1e308, duration=2, easing=lambda t: 10)
    with pytest.raises(ValueError, match="interpolated value"):
        tween.update(1)
    assert tween.value == 1e308 and not tween.done


def test_properties_are_read_only():
    tween = Tween(1, 15, duration=2)
    for name in ("value", "done"):
        with pytest.raises(AttributeError):
            setattr(tween, name, 0)


@pytest.mark.parametrize("name", ease.__all__)
def test_standard_easing_endpoints_finiteness_and_symmetry(name):
    function = getattr(ease, name)
    assert function(0) == pytest.approx(0, abs=1e-14)
    assert function(1) == pytest.approx(1, abs=1e-14)
    assert all(math.isfinite(function(i / 1000)) for i in range(1001))
    if name.startswith("in_out_"):
        assert function(.5) == pytest.approx(.5)
        for t in (.1, .25, .4):
            assert function(t) == pytest.approx(1 - function(1 - t))
    elif name.startswith("in_"):
        out = getattr(ease, "out_" + name[3:])
        assert function(.25) == pytest.approx(1 - out(.75))


@pytest.mark.parametrize("family", ["sine", "quad", "cubic", "quart", "quint", "expo", "circ"])
def test_bounded_easing_families_are_monotonic(family):
    for direction in ("in", "out", "in_out"):
        values = [getattr(ease, f"{direction}_{family}")(i / 100) for i in range(101)]
        assert values == sorted(values)
        assert min(values) >= -1e-14 and max(values) <= 1 + 1e-14


def test_easing_inventory_and_known_samples():
    assert len(ease.__all__) == len(set(ease.__all__)) == 31
    assert ease.linear(.25) == .25
    assert ease.in_quad(.25) == .0625
    assert ease.out_cubic(.5) == .875
    assert ease.out_bounce(1 / 2.75) == pytest.approx(1)
    assert ease.in_back(.25) < 0
    assert ease.out_back(.75) > 1
    assert min(ease.in_elastic(i / 100) for i in range(101)) < 0
    assert max(ease.out_elastic(i / 100) for i in range(101)) > 1


def test_real_dynamic_circle_growth_no_static_invalidation_and_bounds_errors():
    registry = TileResourceRegistry.for_space(pymunk.Space())
    builder = TileBuilder(registry, 1, (0, 0))
    active = SimpleNamespace(owner_id=1, builder=builder)
    engine = SimpleNamespace(registry=registry, active_tiles={(0, 0): active}, balls=[])
    exporter = SceneExporter(engine)
    circle = builder.visual_circle((200, 200), 1, dynamic=True)
    exporter.sync()
    revision = builder.visual_revision
    tween = Tween(1, 15, duration=2, apply=circle.set_radius, easing=ease.in_out_sine)
    for _ in range(4):
        tween.update(.5)
        event, = exporter.sync()
        assert event[0] == "tile_dynvisuals"
        assert event[2][0][3] == tween.value
    assert tween.done and tween.value == 15 and builder.visual_revision == revision
    invalid = Tween(15, 300, duration=1, apply=circle.set_radius)
    with pytest.raises(GeometryBoundsError):
        invalid.update(1)
    assert not invalid.done and invalid.value == 15
    assert registry.resolve(1, circle).radius == 15
