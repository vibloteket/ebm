from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Type

from .tile_base import TileBase, tile_class_from_module, tile_display_name


@dataclass(frozen=True)
class TileRegistration:
    module: str
    tile_class: Type[TileBase]
    builtin: bool = True

    @property
    def id(self) -> str:
        """Stable system identity derived from the module path."""
        return self.module.removeprefix("ebm.tiles.").replace("_", "-")

    @property
    def title(self) -> str:
        return tile_display_name(self.tile_class)

    def create(self) -> TileBase:
        return self.tile_class()


_BUILTIN_MODULES = (
    "ebm.tiles.builtin.powered_channel",
    "ebm.tiles.builtin.reference_router",
)
_CONTRIBUTED_MODULES = (
    "ebm.tiles.contributed.segment_switchback",
)


def _load_registration(module_name: str, *, builtin: bool = True) -> TileRegistration:
    module = import_module(module_name)
    tile_class = tile_class_from_module(module)
    if not isinstance(tile_class.author, str) or not tile_class.author.strip() or tile_class.author == TileBase.author:
        raise ValueError(f"{module_name} must declare an author")
    return TileRegistration(module_name, tile_class, builtin)


_REGISTRATIONS = (
    *(_load_registration(name) for name in _BUILTIN_MODULES),
    *(_load_registration(name, builtin=False) for name in _CONTRIBUTED_MODULES),
)
_BY_ID = {registration.id: registration for registration in _REGISTRATIONS}
if len(_BY_ID) != len(_REGISTRATIONS):
    raise ValueError("duplicate generated tile id in catalog")


def all_tiles() -> tuple[TileRegistration, ...]:
    return _REGISTRATIONS


def get_tile(tile_id: str) -> TileRegistration:
    try:
        return _BY_ID[tile_id]
    except KeyError:
        raise KeyError(f"unknown tile id: {tile_id}") from None


def create_tile(tile_id: str) -> TileBase:
    return get_tile(tile_id).create()


def default_tile() -> TileBase:
    return create_tile("builtin.powered-channel")
