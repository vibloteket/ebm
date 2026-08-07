from ebm.ports import BALL_RADIUS, INPUT_PORTS, MIRROR_PORT, OUTPUT_PORTS, PORT_APERTURE, PORT_CENTER_RANGE, PORT_SPECS, Port


def test_port_sets_and_mirrors():
    assert INPUT_PORTS == {Port.T0, Port.L0, Port.R0}
    assert OUTPUT_PORTS == {Port.B0, Port.L1, Port.R1}
    assert MIRROR_PORT[Port.B0] is Port.T0
    assert MIRROR_PORT[Port.R1] is Port.L0
    assert MIRROR_PORT[Port.L1] is Port.R0


def test_all_ports_share_120_unit_physical_aperture():
    assert BALL_RADIUS == 15
    assert PORT_APERTURE == 120
    assert PORT_CENTER_RANGE == 45
    for port, spec in PORT_SPECS.items():
        along_range = spec.x_range if port in (Port.T0, Port.B0) else spec.y_range
        assert 2 * along_range + 2 * BALL_RADIUS == PORT_APERTURE
