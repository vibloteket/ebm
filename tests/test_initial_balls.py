from ebm.engine import Engine
from ebm.ports import Port, TILE_SIZE


def cleanup(engine):
    for ball in list(engine.balls):engine.remove_ball(ball)
    for active in list(engine.active_tiles.values()):engine.registry.destroy_owner(active.owner_id)


def test_initial_state_has_one_ball_at_every_active_tile_input():
    engine=Engine(300,240);assert engine.balls==[]
    engine.resize(1200,800)
    assert len(engine.balls)==len(engine.active_tiles)*3
    positions={(round(float(b.body.position.x),3),round(float(b.body.position.y),3)) for b in engine.balls}
    assert len(positions)==len(engine.balls)
    cleanup(engine)


def test_pan_preserves_overlapping_balls_and_spawns_only_at_new_boundary():
    engine=Engine(300,240);engine.resize(800,600)
    tracked=engine.balls[len(engine.balls)//2];tracked_id=id(tracked);old_position=tuple(tracked.body.position)
    engine.pan(100,0)
    # Camera operations no longer redistribute or teleport existing balls.
    assert any(id(ball)==tracked_id and tuple(ball.body.position)==old_position for ball in engine.balls)
    assert set(engine._spawn_clocks)==engine._boundary_inputs()
    cleanup(engine)


def test_fast_pan_immediately_seeds_every_new_tile_input():
    engine=Engine(300,240);engine.resize(800,600)
    old_tiles=set(engine.active_tiles);old_ball_ids={id(ball) for ball in engine.balls}
    engine.pan(3*TILE_SIZE,0)
    new_tiles=set(engine.active_tiles)-old_tiles
    assert new_tiles
    # Each new tile is seeded synchronously during reconciliation; no frame or
    # boundary-spawn interval is required.
    for row,col in new_tiles:
        for port in (Port.T0,Port.L0,Port.R0):
            x,y,_=engine._port_state(row,col,port)
            assert any(abs(float(ball.body.position.x)-x)<.01 and abs(float(ball.body.position.y)-y)<.01 for ball in engine.balls)
    assert any(id(ball) in old_ball_ids for ball in engine.balls)
    cleanup(engine)


def test_boundary_inputs_match_unconnected_outer_edges():
    engine=Engine(300,240);engine.resize(800,600)
    coords=set(engine.active_tiles);boundary=engine._boundary_inputs()
    for row,col,port in boundary:
        if port==Port.T0:assert(row-1,col)not in coords
        elif port==Port.L0:assert(row,col-1)not in coords
        else:assert(row,col+1)not in coords
    assert boundary
    cleanup(engine)
