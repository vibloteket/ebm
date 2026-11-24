import pymunk
import pytest

from ebm.physics_config import set_solver, solver_info


def test_default_is_baseline():
    space = pymunk.Space()
    set_solver(space, "baseline")
    assert solver_info(space) == {
        "version": pymunk.version, "solver": "baseline", "solver_supported": hasattr(pymunk, "SolverMode")
    }


@pytest.mark.skipif(not hasattr(pymunk, "SolverMode"), reason="Pymunk 7.4 API")
def test_switch_live_and_step():
    space = pymunk.Space()
    body = pymunk.Body(1, 10)
    space.add(body, pymunk.Circle(body, 5))
    space.gravity = (0, 100)
    for mode in ("auto", "baseline", "auto"):
        set_solver(space, mode)
        assert solver_info(space)["solver"] == mode
        space.step(1 / 60)
    assert body.velocity.y > 0


def test_invalid_mode_does_not_change_solver():
    space = pymunk.Space()
    with pytest.raises(ValueError, match="Unsupported solver"):
        set_solver(space, "anything")
    assert solver_info(space)["solver"] == "baseline"


def test_legacy_api(monkeypatch):
    space = pymunk.Space()
    monkeypatch.delattr(pymunk, "SolverMode", raising=False)
    set_solver(space, "baseline")
    assert solver_info(space)["solver"] == "baseline"
    assert not solver_info(space)["solver_supported"]
    with pytest.raises(ValueError, match="requires Pymunk 7.4"):
        set_solver(space, "auto")
