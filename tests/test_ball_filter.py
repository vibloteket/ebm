from ebm.engine import Engine
from ebm.tile_api import BALL_ELASTICITY, BALL_FRICTION


def test_engine_balls_use_shared_material_properties():
    engine=Engine(300,240)
    ball=engine.add_ball(100,100)
    assert ball.shape.friction == BALL_FRICTION
    assert ball.shape.elasticity == BALL_ELASTICITY
    engine.remove_ball(ball)
    for active in list(engine.active_tiles.values()):engine.registry.destroy_owner(active.owner_id)


def test_balls_collide_with_each_other():
    engine=Engine(300,240);engine.resize(300,240)
    for ball in list(engine.balls):engine.remove_ball(ball)
    engine.space.gravity = (0, 0)
    left=engine.add_ball(80,100,velocity=(100,0));right=engine.add_ball(120,100,velocity=(-100,0))
    for _ in range(60):engine.space.step(1/240)
    # Equal balls approaching head-on must bounce rather than pass through.
    assert left.body.velocity.x<0
    assert right.body.velocity.x>0
    for ball in list(engine.balls):engine.remove_ball(ball)
    for active in list(engine.active_tiles.values()):engine.registry.destroy_owner(active.owner_id)
