import pytest

from ebm.tile_api import ShapeHandle, TileBuilder, TileResourceRegistry


def make_builders():
    import pymunk
    space=pymunk.Space();registry=TileResourceRegistry.for_space(space)
    return space,registry,TileBuilder(registry,1,(0,0)),TileBuilder(registry,2,(400,0))


def test_builder_exposes_no_space_and_enforces_bounds():
    _,_,tile,_=make_builders()
    assert not hasattr(tile,"space")
    with pytest.raises(ValueError):tile.static_segment((-21,0),(10,10),3)
    with pytest.raises(ValueError):tile.static_circle((5,5),30)


def test_resource_ownership_is_enforced():
    _,registry,left,right=make_builders();shape=left.static_segment((10,10),(190,10),3)
    with pytest.raises(PermissionError):registry.resolve(2,shape)
    with pytest.raises(PermissionError):right.remove(shape)


def test_owner_cleanup_removes_all_resources_and_callbacks():
    space,registry,tile,_=make_builders();baseline=(len(space.bodies),len(space.shapes),len(space.constraints))
    tile.static_circle((100,100),20);sensor=tile.sensor_box(10,10,190,190);tile.on_ball_contact(sensor, begin=lambda event:None)
    assert len(space.shapes)>baseline[1]
    registry.destroy_owner(1)
    assert (len(space.bodies),len(space.shapes),len(space.constraints))==baseline


def test_static_polygon_builds_visible_colliding_geometry():
    _, registry, tile, _ = make_builders()
    handle = tile.static_polygon(((40, 40), (160, 40), (100, 120)))
    shape = registry.resolve(1, handle)
    assert type(shape).__name__ == "Poly"
    assert len(shape.get_vertices()) == 3
    assert any(item[0] is shape for item in tile.visual_items)


def test_dynamic_compound_body_pivot_motor_and_mutation():
    import pymunk

    space, registry, tile, _ = make_builders()
    wheel = tile.dynamic_body((200, 200))
    tile.circle_shape(wheel, (0, 0), 25, density=.02)
    tile.segment_shape(wheel, (-70, 0), (70, 0), 5, density=.01)
    tile.polygon_shape(wheel, ((-8, 35), (8, 35), (8, 75), (-8, 75)), density=.01)
    tile.pivot(wheel, (200, 200))
    motor = tile.motor(wheel, rate=2, max_force=5000)

    raw_body = registry.resolve(1, wheel)
    raw_motor = registry.resolve(1, motor)
    assert raw_body.mass > 0 and raw_body.moment > 0
    assert len(space.shapes) == 3 and len(space.constraints) == 2

    assert wheel.position == pytest.approx((200, 200))
    wheel.set_velocity((10, 20)); wheel.set_angle(.25); wheel.set_angular_velocity(1)
    wheel.apply_force((100, 0)); wheel.apply_impulse((2, 0)); wheel.apply_torque(3)
    motor.set_rate(-1.5); motor.set_max_force(900)
    assert wheel.velocity[0] > 10 and wheel.velocity[1] > 20
    assert wheel.angle == pytest.approx(.25)
    assert wheel.angular_velocity > 1
    assert raw_motor.rate == pytest.approx(-1.5)
    assert raw_motor.max_force == pytest.approx(900)

    for _ in range(10): space.step(1/60)
    assert raw_body.angle != pytest.approx(.25)


def test_pausing_dynamic_body_pauses_and_restores_complete_mechanism():
    space, registry, tile, _ = make_builders()
    body = tile.dynamic_body((100, 100))
    shape = tile.circle_shape(body, (0, 0), 20)
    pivot = tile.pivot(body, (100, 100))
    motor = tile.motor(body, rate=1, max_force=100)
    raw = [registry.resolve(1, handle) for handle in (body, shape, pivot, motor)]

    body.pause()
    assert all(item not in space.bodies and item not in space.shapes and item not in space.constraints for item in raw)
    assert tile.visual_items == []
    body.resume()
    assert raw[0] in space.bodies and raw[1] in space.shapes
    assert raw[2] in space.constraints and raw[3] in space.constraints


def test_compound_body_is_removed_cleanly_with_owner():
    space, registry, tile, _ = make_builders()
    baseline = (len(space.bodies), len(space.shapes), len(space.constraints))
    body = tile.dynamic_body((200, 200))
    tile.circle_shape(body, (0, 0), 30)
    tile.segment_shape(body, (-50, 0), (50, 0), 4)
    tile.pivot(body, (200, 200))
    tile.motor(body, rate=1, max_force=1000)
    registry.destroy_owner(1)
    assert (len(space.bodies), len(space.shapes), len(space.constraints)) == baseline
