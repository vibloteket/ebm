"""Main-machine solver configuration; other entry points do not use this."""

import pymunk


def set_solver(space: pymunk.Space, mode: str) -> None:
    if mode not in ("baseline", "auto"):
        raise ValueError(f"Unsupported solver: {mode}")
    if not hasattr(pymunk, "SolverMode"):
        if mode != "baseline":
            raise ValueError("Solver selection requires Pymunk 7.4 or later")
        return
    space.solver_mode = (
        pymunk.SolverMode.AUTO if mode == "auto" else pymunk.SolverMode.BASELINE
    )


def solver_info(space: pymunk.Space) -> dict:
    supported = hasattr(pymunk, "SolverMode")
    mode = "auto" if supported and space.solver_mode == pymunk.SolverMode.AUTO else "baseline"
    return {"version": pymunk.version, "solver": mode, "solver_supported": supported}
