from ebm.ports import INPUT_PORTS, MIRROR_PORT, OUTPUT_PORTS, Port, RoutePermutation
from ebm.routes import ALL_ROUTES, DEFAULT_ROUTES, route_at, route_selection_at


def test_all_six_bijective_routes_exist():
    assert len(ALL_ROUTES) == 6
    assert len({route.key for route in ALL_ROUTES}) == 6
    for route in ALL_ROUTES:
        assert route.entries == (Port.T0, Port.L0, Port.R0)
        assert set(route.exits) == {Port.B0, Port.L1, Port.R1}


def test_default_routes_avoid_same_side_returns():
    assert len(DEFAULT_ROUTES) == 3
    for route in DEFAULT_ROUTES:
        assert route.exit_for(Port.L0) is not Port.L1
        assert route.exit_for(Port.R0) is not Port.R1


def test_route_field_is_deterministic_and_uses_all_defaults():
    first=[route_at(r,c).key for r in range(-20,21) for c in range(-20,21)]
    second=[route_at(r,c).key for r in range(-20,21) for c in range(-20,21)]
    assert first == second
    assert set(first) == {route.key for route in DEFAULT_ROUTES}


def test_route_and_implementation_selection_are_separate():
    selections=[route_selection_at(r,c) for r in range(-10,11) for c in range(-10,11)]
    assert {item.route.key for item in selections} == {route.key for route in DEFAULT_ROUTES}
    assert len({item.implementation_seed for item in selections}) > 400


def test_route_permutation_rejects_non_bijections():
    try:
        RoutePermutation((Port.B0, Port.B0, Port.L1))
    except ValueError:
        pass
    else:
        raise AssertionError("non-bijective route accepted")


def test_port_sets_and_mirrors():
    assert INPUT_PORTS == {Port.T0, Port.L0, Port.R0}
    assert OUTPUT_PORTS == {Port.B0, Port.L1, Port.R1}
    assert MIRROR_PORT[Port.B0] is Port.T0
    assert MIRROR_PORT[Port.R1] is Port.L0
    assert MIRROR_PORT[Port.L1] is Port.R0
