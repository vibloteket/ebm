import pytest

from ebm.tile_api import (
    DEFAULT_CIRCLE_FILL,
    DEFAULT_CIRCLE_STROKE,
    TileBuilder,
    TileResourceRegistry,
    VisualHandle,
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
