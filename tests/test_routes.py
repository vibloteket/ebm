from ebm.ports import BALL_RADIUS, INPUT_PORTS, MIRROR_PORT, OUTPUT_PORTS, PORT_APERTURE, PORT_CENTER_RANGE, PORT_SPECS, Port, left_neighbor, right_neighbor, tile_origin


def test_port_sets_and_mirrors():
    assert INPUT_PORTS == {Port.T0, Port.L0}
    assert OUTPUT_PORTS == {Port.B0, Port.R0}
    assert MIRROR_PORT[Port.B0] is Port.T0
    assert MIRROR_PORT[Port.R0] is Port.L0
    assert MIRROR_PORT[Port.L0] is Port.R0


def test_staggered_neighbors_align_and_always_progress_right():
    for row in range(-2, 3):
        for col in range(-2, 3):
            next_row, next_col = right_neighbor(row, col)
            assert next_col == col + 1
            assert left_neighbor(next_row, next_col) == (row, col)
            x, y = tile_origin(row, col)
            nx, ny = tile_origin(next_row, next_col)
            assert (x + Port.R0.point[0], y + Port.R0.point[1]) == (
                nx + Port.L0.point[0], ny + Port.L0.point[1]
            )


def test_all_ports_share_120_unit_physical_aperture():
    assert BALL_RADIUS == 15
    assert PORT_APERTURE == 120
    assert PORT_CENTER_RANGE == 45
    for port, spec in PORT_SPECS.items():
        along_range = spec.x_range if port in (Port.T0, Port.B0) else spec.y_range
        assert 2 * along_range + 2 * BALL_RADIUS == PORT_APERTURE
