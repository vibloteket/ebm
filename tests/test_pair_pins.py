import pymunk
import pytest

from ebm.tile_api import (
    BALL_CATEGORY,
    TileBuilder,
    TileResourceRegistry,
    ball_shape_filter,
)


def world():
    space = pymunk.Space()
    space.gravity = (0, 900)
    registry = TileResourceRegistry.for_space(space)
    return space, registry, TileBuilder(registry, 1, (0, 0))


def link(tile, y):
    body = tile.dynamic_body((200, y))
    tile.circle_shape(body, (0, 0), 6)
    return body


def raw(registry, handle):
    return registry.resolve(1, handle)


def shape_of(registry, handle):
    (shape,) = list(raw(registry, handle).shapes)
    return shape


def step(space, frames=60):
    for _ in range(frames):
        space.step(1 / 60)


def add_ball(space, registry, position=(200, 300)):
    body = pymunk.Body(1, pymunk.moment_for_circle(1, 0, 8))
    body.position = position
    shape = pymunk.Circle(body, 8)
    shape.friction = 0.45
    shape.elasticity = 0.8
    shape.ebm_fill_color = (22, 114, 212, 255)
    shape.ebm_stroke_color = (12, 63, 143, 255)
    shape.collision_type = 1
    shape.filter = ball_shape_filter()
    space.add(body, shape)
    return registry._claim_ball(1, body, shape)


def ball_record(registry, ball):
    return registry._balls[ball._body]


def test_static_pin_form_still_works():
    space, registry, tile = world()
    body = link(tile, 100)
    tile.pivot(body, (200, 100))
    step(space, 120)
    assert raw(registry, body).position.y == pytest.approx(100, abs=1)


def test_pair_pin_builds_a_hanging_chain():
    space, registry, tile = world()
    links = [link(tile, 60 + 40 * i) for i in range(4)]
    tile.pivot(links[0], (200, 60))
    for i, (a, b) in enumerate(zip(links, links[1:])):
        tile.pivot(a, b, (200, 60 + 40 * i + 20))
    step(space, 180)
    positions = [raw(registry, body_).position for body_ in links]
    # Chain holds: consecutive links stay roughly one link-length apart.
    for (x1, y1), (x2, y2) in zip(positions, positions[1:]):
        assert abs((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 == pytest.approx(40, abs=8)
    # And it hangs downward from the anchor rather than falling away.
    assert 50 < positions[0].y < 200
    assert positions[-1].y > positions[0].y


def test_pair_pin_disables_collision_transitively():
    space, registry, tile = world()
    a, b, c = link(tile, 60), link(tile, 100), link(tile, 140)
    other = link(tile, 300)
    tile.pivot(a, b, (200, 80))
    tile.pivot(b, c, (200, 120))
    groups = {shape_of(registry, body_).filter.group for body_ in (a, b, c)}
    (group,) = groups
    assert group != 0
    assert shape_of(registry, other).filter.group == 0


def test_pair_pin_with_collide_true_keeps_default_group():
    space, registry, tile = world()
    a, b = link(tile, 60), link(tile, 100)
    tile.pivot(a, b, (200, 80), collide=True)
    assert shape_of(registry, a).filter.group == 0
    assert shape_of(registry, b).filter.group == 0


def test_glue_ball_without_point_does_not_jump():
    space, registry, tile = world()
    body = link(tile, 150)
    tile.pivot(body, (200, 150))
    ball = add_ball(space, registry, (220, 260))
    tile.pivot(body, ball)
    assert ball.position == pytest.approx((220, 260), abs=1e-6)
    step(space, 120)
    # The ball stays glued instead of falling.
    assert ball.position == pytest.approx((220, 260), abs=6)


def test_glue_ball_with_point_snaps_center():
    space, registry, tile = world()
    body = link(tile, 150)
    tile.pivot(body, (200, 150))
    ball = add_ball(space, registry, (220, 260))
    tile.pivot(body, ball, (200, 200))
    step(space, 120)
    # The link rotates freely around its world pin, so the ball settles
    # somewhere on the 50-unit circle around the anchor instead of falling.
    x, y = ball_record(registry, ball)["body"].position
    assert abs((x - 200) ** 2 + (y - 150) ** 2) ** 0.5 == pytest.approx(50, abs=3)


def test_glue_keeps_ball_categories_and_release_restores_filter():
    space, registry, tile = world()
    body = link(tile, 150)
    tile.pivot(body, (200, 150))
    ball = add_ball(space, registry, (220, 260))
    shape = ball_record(registry, ball)["shape"]
    before = shape.filter
    tile.pivot(body, ball)
    assert shape.filter.group != 0
    assert shape.filter.categories == before.categories == BALL_CATEGORY
    registry._release_ball(ball_record(registry, ball))
    assert shape.filter.group == 0
    assert shape.filter.categories == BALL_CATEGORY


def test_release_breaks_glue_and_ball_falls():
    space, registry, tile = world()
    body = link(tile, 150)
    tile.pivot(body, (200, 150))
    ball = add_ball(space, registry, (220, 260))
    pin = tile.pivot(body, ball)
    registry._release_ball(ball_record(registry, ball))
    assert pin.id not in registry._objects
    assert len(space.constraints) == 1  # Only the link's static world pin remains.
    step(space, 60)
    y = ball_record(registry, ball)["body"].position.y
    assert y > 300


def test_remove_detaches_and_kills_the_handle():
    space, registry, tile = world()
    body = link(tile, 150)
    tile.pivot(body, (200, 150))
    ball = add_ball(space, registry, (220, 260))
    pin = tile.pivot(body, ball)
    tile.remove(pin)
    step(space, 60)
    assert ball_record(registry, ball)["body"].position.y > 280
    with pytest.raises(PermissionError):
        tile.remove(pin)


def test_pause_pinned_ball_raises():
    space, registry, tile = world()
    body = link(tile, 150)
    tile.pivot(body, (200, 150))
    ball = add_ball(space, registry, (220, 260))
    tile.pivot(body, ball)
    with pytest.raises(RuntimeError, match="pinned"):
        ball.pause()


def test_pause_body_holding_a_ball_pin_raises():
    space, registry, tile = world()
    body = link(tile, 150)
    tile.pivot(body, (200, 150))
    ball = add_ball(space, registry, (220, 260))
    pin = tile.pivot(body, ball)
    with pytest.raises(RuntimeError, match="pins a ball"):
        body.pause()
    tile.remove(pin)
    body.pause()  # After detach, pausing works again.


def test_pin_validation_errors():
    space, registry, tile = world()
    a, b = link(tile, 60), link(tile, 100)
    with pytest.raises(ValueError):
        tile.pivot(a, b)  # two bodies need a point
    with pytest.raises(ValueError):
        tile.pivot(a, a, (200, 80))  # cannot pin a body to itself
    with pytest.raises(ValueError):
        tile.pivot(a, (200, 60), point=(200, 80))  # static form takes no point
    with pytest.raises(ValueError):
        tile.pivot(a, (200, 60), collide=True)  # collide needs a pair
    _, _, tile2 = world()[0], None, TileBuilder(registry, 2, (400, 0))
    foreign = link(tile2, 60)
    with pytest.raises(PermissionError):
        tile.pivot(a, foreign, (200, 80))


def test_pauses_of_a_rope_link_take_shared_pins_along():
    space, registry, tile = world()
    a, b, c = link(tile, 60), link(tile, 100), link(tile, 140)
    pin_ab = tile.pivot(a, b, (200, 80))
    pin_bc = tile.pivot(b, c, (200, 120))
    b.pause()
    assert raw(registry, pin_ab) not in space.constraints
    assert raw(registry, pin_bc) not in space.constraints
    b.resume()
    assert raw(registry, pin_ab) in space.constraints
    assert raw(registry, pin_bc) in space.constraints
    step(space, 60)  # Chain is still intact afterwards.
    positions = [raw(registry, body_).position for body_ in (a, b, c)]
    for (x1, y1), (x2, y2) in zip(positions, positions[1:]):
        assert abs((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 == pytest.approx(40, abs=12)


def test_destroy_owner_releases_glued_ball():
    space, registry, tile = world()
    body = link(tile, 150)
    tile.pivot(body, (200, 150))
    ball = add_ball(space, registry, (220, 260))
    tile.pivot(body, ball)
    shape = ball_record(registry, ball)["shape"]
    registry.destroy_owner(1)
    assert not space.constraints
    assert shape.filter.group == 0
    with pytest.raises(PermissionError):
        ball.position  # Handle is dead after teardown.
    step(space, 60)
    assert shape.body.position.y > 280
