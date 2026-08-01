from ebm.ports import INPUT_PORTS, MIRROR_PORT, OUTPUT_PORTS, Port


def test_port_sets_and_mirrors():
    assert INPUT_PORTS == {Port.T0, Port.L0, Port.R0}
    assert OUTPUT_PORTS == {Port.B0, Port.L1, Port.R1}
    assert MIRROR_PORT[Port.B0] is Port.T0
    assert MIRROR_PORT[Port.R1] is Port.L0
    assert MIRROR_PORT[Port.L1] is Port.R0
