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
