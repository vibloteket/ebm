from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Type

from .ports import RoutePermutation
from .tile_base import TileBase


@dataclass(frozen=True)
class TileRegistration:
    module: str
    tile_class: Type[TileBase]
    builtin: bool = True

    @property
    def id(self) -> str:
        return self.tile_class.id

    def create(self, route: RoutePermutation) -> TileBase:
        if route not in self.tile_class.routes:
            raise ValueError(f"{self.id} does not support route: {route}")
        return self.tile_class(route)


_BUILTIN_MODULES = (
    "ebm.tiles.builtin.powered_channel",
    "ebm.tiles.builtin.reference_router",
)


def _load_registration(module_name: str, *, builtin: bool = True) -> TileRegistration:
    module = import_module(module_name)
    tile_class = getattr(module, "TILE_CLASS", None)
    if not isinstance(tile_class, type) or not issubclass(tile_class, TileBase):
        raise TypeError(f"{module_name} must export a TileBase subclass as TILE_CLASS")
    if not tile_class.id or tile_class.id == TileBase.id:
        raise ValueError(f"{module_name} must declare a unique tile id")
    if tile_class.api_version != 1:
        raise ValueError(f"{tile_class.id} uses unsupported API version {tile_class.api_version}")
    if not tile_class.routes:
        raise ValueError(f"{tile_class.id} must declare at least one route")
    return TileRegistration(module_name, tile_class, builtin)


_REGISTRATIONS = tuple(_load_registration(name) for name in _BUILTIN_MODULES)
_BY_ID = {registration.id: registration for registration in _REGISTRATIONS}
if len(_BY_ID) != len(_REGISTRATIONS):
    raise ValueError("duplicate tile id in catalog")


def all_tiles() -> tuple[TileRegistration, ...]:
    return _REGISTRATIONS


def get_tile(tile_id: str) -> TileRegistration:
    try:
        return _BY_ID[tile_id]
    except KeyError:
        raise KeyError(f"unknown tile id: {tile_id}") from None


def candidates_for(route: RoutePermutation) -> tuple[TileRegistration, ...]:
    return tuple(item for item in _REGISTRATIONS if route in item.tile_class.routes)


def create_tile(tile_id: str, route: RoutePermutation) -> TileBase:
    return get_tile(tile_id).create(route)


def tile_for_route(route: RoutePermutation) -> TileBase:
    preferred = "ebm.powered-channel" if route in get_tile("ebm.powered-channel").tile_class.routes else "ebm.reference-router"
    return create_tile(preferred, route)
