import pytest

from ebm.tile_api import (
    DEFAULT_BALL_FILL,
    DEFAULT_BALL_STROKE,
    DEFAULT_CIRCLE_FILL,
    DEFAULT_CIRCLE_STROKE,
    DEFAULT_SEGMENT_STROKE,
    TileBuilder,
    TileResourceRegistry,
    VisualHandle,
    ball_shape_filter,
)


def builder():
    import pymunk

    space = pymunk.Space()
    registry = TileResourceRegistry.for_space(space)
    return registry, TileBuilder(registry, 1, (0, 0))


def test_all_visible_shapes_share_mutable_fill_and_stroke_colors():
    registry, tile = builder()
    segment = tile.static_segment((10, 10), (190, 10), fill_color=(1, 2, 3, 4), stroke_color=(5, 6, 7, 8))
    circle = tile.static_circle((100, 100), 20)
    visual = tile.visual_segment((10, 20), (190, 20))
    assert isinstance(visual, VisualHandle)

    segment.set_fill_color((10, 20, 30, 40))
    circle.set_stroke_color((50, 60, 70, 80))
    visual.set_fill_color((90, 100, 110, 120))

    styles = {type(obj).__name__: style for obj, style in tile.visual_items}
    assert styles["Segment"].fill_color == (10, 20, 30, 40)
    assert styles["Circle"].fill_color == DEFAULT_CIRCLE_FILL
    assert styles["Circle"].stroke_color == (50, 60, 70, 80)
    assert styles["VisualSegment"].fill_color == (90, 100, 110, 120)
    assert tile.visual_revision == 3


def test_setting_same_color_does_not_invalidate_render_cache():
    _, tile = builder()
    circle = tile.static_circle((100, 100), 20)
    circle.set_fill_color(DEFAULT_CIRCLE_FILL)
    circle.set_stroke_color(DEFAULT_CIRCLE_STROKE)
    assert tile.visual_revision == 0


def test_colors_require_four_integer_components_from_zero_to_255():
    _, tile = builder()
    with pytest.raises(ValueError):
        tile.static_segment((10, 10), (190, 10), fill_color=(1, 2, 3))
    with pytest.raises(ValueError):
        tile.static_circle((100, 100), 20, stroke_color=(0, 0, 0, 256))
    with pytest.raises(ValueError):
        tile.visual_segment((10, 10), (190, 10), fill_color=(1.0, 2, 3, 4))


def test_handle_rejects_mutation_after_owner_cleanup():
    registry, tile = builder()
    shape = tile.static_circle((100, 100), 20)
    registry.destroy_owner(1)
    with pytest.raises(PermissionError):
        shape.set_fill_color((1, 2, 3, 4))


def test_builder_has_no_duplicate_color_setters():
    _, tile = builder()
    assert not hasattr(tile, "set_fill_color")
    assert not hasattr(tile, "set_stroke_color")


CLEAR = (0, 0, 0, 0)


def test_none_means_unpainted_and_normalizes_to_transparent():
    _, tile = builder()
    tile.static_segment((10, 10), (190, 10), fill_color=None)
    tile.static_circle((100, 100), 20, stroke_color=None)
    tile.static_polygon([(20, 20), (60, 20), (40, 60)], fill_color=None, stroke_color=None)
    tile.visual_segment((10, 30), (190, 30), fill_color=None)
    styles = {type(obj).__name__: style for obj, style in tile.visual_items}
    assert styles["Segment"].fill_color == CLEAR
    assert styles["Segment"].stroke_color == DEFAULT_SEGMENT_STROKE
    assert styles["Circle"].fill_color == DEFAULT_CIRCLE_FILL
    assert styles["Circle"].stroke_color == CLEAR
    assert styles["Poly"].fill_color == CLEAR
    assert styles["Poly"].stroke_color == CLEAR
    assert styles["VisualSegment"].fill_color == CLEAR
    assert styles["VisualSegment"].stroke_color == DEFAULT_SEGMENT_STROKE


def test_setters_clear_paint_layers_with_none():
    _, tile = builder()
    circle = tile.static_circle((100, 100), 20)
    circle.set_fill_color(None)
    circle.set_stroke_color(None)
    (style,) = [style for _, style in tile.visual_items]
    assert style.fill_color == CLEAR
    assert style.stroke_color == CLEAR


def test_clearing_then_resetting_same_color_keeps_render_cache_stable():
    _, tile = builder()
    circle = tile.static_circle((100, 100), 20)
    circle.set_fill_color(None)
    assert tile.visual_revision == 1
    circle.set_fill_color(None)  # Already unpainted: no change, no invalidation.
    assert tile.visual_revision == 1


def test_ball_style_none_clears_and_omitted_leaves_unchanged():
    import pymunk

    space = pymunk.Space()
    registry = TileResourceRegistry.for_space(space)
    TileBuilder(registry, 1, (0, 0))
    body = pymunk.Body(1, pymunk.moment_for_circle(1, 0, 8))
    body.position = (100, 100)
    shape = pymunk.Circle(body, 8)
    shape.filter = ball_shape_filter()
    shape.ebm_fill_color = DEFAULT_BALL_FILL
    shape.ebm_stroke_color = DEFAULT_BALL_STROKE
    space.add(body, shape)
    ball = registry._claim_ball(1, body, shape)

    ball.set_fill_color(None)
    assert shape.ebm_fill_color == CLEAR
    assert shape.ebm_stroke_color == DEFAULT_BALL_STROKE  # Untouched.
    ball.set_stroke_color(None)
    assert shape.ebm_stroke_color == CLEAR
