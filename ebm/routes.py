from __future__ import annotations

from dataclasses import dataclass

from .ports import Port, RoutePermutation
from .random_utils import stable_rng

WORLD_SEED = 42

ALL_ROUTES = tuple(
    RoutePermutation(exits)
    for exits in (
        (Port.B0, Port.L1, Port.R1),
        (Port.B0, Port.R1, Port.L1),
        (Port.L1, Port.B0, Port.R1),
        (Port.L1, Port.R1, Port.B0),
        (Port.R1, Port.B0, Port.L1),
        (Port.R1, Port.L1, Port.B0),
    )
)

DEFAULT_ROUTES = (ALL_ROUTES[1], ALL_ROUTES[3], ALL_ROUTES[4])


@dataclass(frozen=True)
class RouteSelection:
    route: RoutePermutation
    implementation_seed: int


def route_selection_at(row: int, col: int, world_seed: int = WORLD_SEED) -> RouteSelection:
    route_rng = stable_rng("uniform-route", world_seed, row, col)
    route = DEFAULT_ROUTES[route_rng.randrange(len(DEFAULT_ROUTES))]
    seed = stable_rng("tile-implementation", world_seed, row, col).randrange(2**31)
    return RouteSelection(route, seed)


def route_at(row: int, col: int, world_seed: int = WORLD_SEED) -> RoutePermutation:
    return route_selection_at(row, col, world_seed).route
