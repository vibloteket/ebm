import pytest

from ebm.engine import BALL_MASS, BALL_RADIUS
from ebm.routes import ALL_ROUTES, DEFAULT_ROUTES
from ebm.tile_api import BALL_COLLISION_TYPE, TileBuilder, TileResourceRegistry, ball_shape_filter
from ebm.tiles import ReferenceRouterTile
from ebm.validator import validate_filler_route, validate_filler_route_port_spec


@pytest.mark.parametrize("route", ALL_ROUTES)
def test_reference_router_passes_strict_port_spec(route):
    result=validate_filler_route_port_spec(route,duration=12)
    assert result.ok,result.summary()
    assert result.exited==243


@pytest.mark.parametrize("route", DEFAULT_ROUTES)
def test_reference_router_handles_concurrent_balls(route):
    result=validate_filler_route(route,duration=12,balls_per_entry=6)
    assert result.ok,result.summary()
    assert result.exited==18


def test_router_reclassifies_ball_across_tiles():
    import pymunk
    space=pymunk.Space();space.gravity=(0,900);registry=TileResourceRegistry.for_space(space)
    for owner,row in ((1,0),(2,1)):
        ReferenceRouterTile(DEFAULT_ROUTES[0]).build(TileBuilder(registry,owner,(0,row*200)))
    body=pymunk.Body(BALL_MASS,pymunk.moment_for_circle(BALL_MASS,0,BALL_RADIUS));body.position=(100,8.5);body.velocity=(0,90)
    shape=pymunk.Circle(body,BALL_RADIUS);shape.collision_type=BALL_COLLISION_TYPE;shape.filter=ball_shape_filter();space.add(body,shape)
    for _ in range(2400):
        space.step(1/240)
        if body.position.y>208:break
    assert body.ebm_route_origin==(0,200)
    space.remove(shape,body);registry.destroy_owner(1);registry.destroy_owner(2)
