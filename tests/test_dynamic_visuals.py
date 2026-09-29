"""Scene exporter tests: the JS renderer mirrors state via events + poses."""
from types import SimpleNamespace

import pymunk
import pytest

from ebm.scene_export import SceneExporter
from ebm.tile_api import TileBuilder, TileResourceRegistry, VisualHandle


def make_engine(*builders):
    """Minimal engine stand-in with the attributes SceneExporter reads."""
    space = pymunk.Space()
    registry = TileResourceRegistry.for_space(space)
    active = {}
    for owner, origin, build in builders:
        builder = TileBuilder(registry, owner, origin)
        build(builder)
        active[(int(origin[1] // 400), int(origin[0] // 400))] = SimpleNamespace(
            builder=builder, owner_id=owner, tile=object(),
        )
    return SimpleNamespace(space=space, registry=registry, active_tiles=active, balls=[])


def events_of(exporter, kind):
    return [event for event in exporter.sync() if event[0] == kind]


def test_dynamic_visual_segment_exported_outside_statics_and_updated_via_style_events():
    def build(b):
        b.visual_segment((20, 20), (180, 180), 2, dynamic=True)

    engine = make_engine((7, (400, 200), build))
    exporter = SceneExporter(engine)

    (add,) = events_of(exporter, "tile_add")
    kind, owner, ox, oy, statics, dyn_visuals, dyn_bodies = add
    assert (owner, ox, oy) == (7, 400.0, 200.0)
    assert statics == []
    assert len(dyn_visuals) == 1
    assert dyn_visuals[0][:6] == [0, 20.0, 20.0, 180.0, 180.0, 2.0]

    # Dynamic visual changes must not bump the static revision; the JS side
    # gets a lightweight dynvisuals refresh instead of a full tile re-export.
    handle_id = engine.registry._visuals[7][0]
    visual = VisualHandle(handle_id, 7, engine.registry)
    visual.set_segment_points((30, 30), (160, 170))
    visual.set_fill_color((100, 80, 60, 255))
    assert engine.active_tiles[(0, 1)].builder.visual_revision == 0

    (refresh,) = events_of(exporter, "tile_dynvisuals")
    assert refresh[1] == 7
    updated = refresh[2][0]
    assert updated[:6] == [0, 30.0, 30.0, 160.0, 170.0, 2.0]
    assert updated[6] == [100, 80, 60, 255]

    assert events_of(exporter, "tile_style") == []
    assert events_of(exporter, "tile_dynvisuals") == []


def test_kinematic_body_shapes_exported_body_local():
    def build(b):
        pin = b.kinematic_body((100, 100))
        b.segment_shape(pin, (0, 0), (0, -25), 5)

    engine = make_engine((8, (400, 200), build))
    exporter = SceneExporter(engine)

    (add,) = events_of(exporter, "tile_add")
    _, _, ox, oy, statics, _, dyn_bodies = add
    assert statics == []
    assert len(dyn_bodies) == 1
    body_id, shapes = dyn_bodies[0]
    (segment,) = shapes
    assert segment[:6] == [0, 0.0, 0.0, 0.0, -25.0, 5.0]

    # The kinematic body is in the space, so the pose stream carries it.
    ids, floats, stride = exporter.frame()
    count = len(ids) // stride
    streamed = {
        int(ids[i * stride]) + (int(ids[i * stride + 1]) << 32 if stride == 2 else 0)
        for i in range(count)
    }
    assert body_id in streamed
    assert len(floats) == 3 * count


def test_static_style_changes_produce_one_tile_style_per_sync():
    def build(b):
        b.visual_segment((20, 20), (180, 180), 2)

    engine = make_engine((7, (0, 0), build))
    exporter = SceneExporter(engine)
    assert len(events_of(exporter, "tile_add")) == 1

    handle_id = engine.registry._visuals[7][0]
    visual = VisualHandle(handle_id, 7, engine.registry)
    for i in range(100):
        visual.set_segment_points((20 + i / 100, 20), (180, 180))

    (style,) = events_of(exporter, "tile_style")
    assert style[4][0][:6] == [0, 20.99, 20.0, 180.0, 180.0, 2.0]
    assert events_of(exporter, "tile_style") == []
    assert len(exporter._tiles) == 1


def test_tile_removal_and_reactivation_emit_events():
    def build(b):
        b.visual_segment((20, 20), (180, 180), 2)

    engine = make_engine((7, (0, 0), build))
    exporter = SceneExporter(engine)
    events_of(exporter, "tile_add")

    engine.active_tiles.clear()
    (remove,) = events_of(exporter, "tile_remove")
    assert remove == ["tile_remove", 7]
    assert exporter._tiles == {}


def test_ball_events_follow_engine_add_and_remove():
    from ebm.engine import Engine

    engine = Engine(800, 600)
    engine.resize(800, 600)  # seeds initial balls
    exporter = SceneExporter(engine)
    added = events_of(exporter, "ball_add")
    assert len(added) == len(engine.balls) > 0
    first = added[0]
    assert first[0] == "ball_add"
    assert first[2] == pytest.approx(15)  # BALL_RADIUS
    assert first[3] == [22, 114, 212, 255]
    assert first[4] == [12, 63, 143, 255]
    assert first[5] is False

    ball = engine.balls[0]
    engine.remove_ball(ball)
    (remove,) = events_of(exporter, "ball_remove")
    assert remove == ["ball_remove", ball.body.id]
    assert events_of(exporter, "ball_remove") == []


def test_frame_streams_all_body_poses():
    from ebm.engine import Engine

    engine = Engine(800, 600)
    engine.resize(800, 600)
    engine.step_frame(1 / 60)
    exporter = SceneExporter(engine)
    exporter.sync()

    ids, floats, stride = exporter.frame()
    count = len(ids) // stride
    # cpSpaceEachBody also iterates the space's built-in static body, which
    # pymunk's space.bodies property hides.
    assert count == len(engine.space.bodies) + 1
    assert len(floats) == 3 * count
    streamed = {
        int(ids[i * stride]) + (int(ids[i * stride + 1]) << 32 if stride == 2 else 0): i
        for i in range(count)
    }
    for ball in engine.balls:
        i = streamed[ball.body.id]
        assert floats[3 * i] == pytest.approx(ball.body.position.x)
        assert floats[3 * i + 1] == pytest.approx(ball.body.position.y)
