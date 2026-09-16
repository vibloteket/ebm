from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
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
    def enabled(self) -> bool:
        return self.tile_class.enabled

    @property
    def title(self) -> str:
        return tile_display_name(self.tile_class)

    def create(self) -> TileBase:
        return self.tile_class()


def discover_tile_modules(root: Path | None = None) -> tuple[str, ...]:
    """Every public .py file below tiles/ is one tile. Underscore files are helpers.

    Works on disk and in Pyodide's filesystem populated by python-files.json.
    Sorting is part of the deterministic world-selection contract.
    """
    root = root if root is not None else Path(__file__).with_name("tiles")
    modules = []
    for source in root.rglob("*.py"):
        relative = source.relative_to(root).with_suffix("")
        if any(part.startswith("_") for part in relative.parts):
            continue
        if not all(part.isidentifier() for part in relative.parts):
            raise ValueError(f"Tile path must contain valid Python identifiers: {source}")
        modules.append("ebm.tiles." + ".".join(relative.parts))
    return tuple(sorted(modules))


def _load_registration(module_name: str, *, builtin: bool = True) -> TileRegistration:
    module = import_module(module_name)
    tile_class = tile_class_from_module(module)
    if not isinstance(tile_class.author, str) or not tile_class.author.strip() or tile_class.author == TileBase.author:
        raise ValueError(f"{module_name} must declare an author")
    if type(tile_class.enabled) is not bool:
        raise ValueError(f"{module_name}: enabled must be True or False")
    return TileRegistration(module_name, tile_class, builtin)


_REGISTRATIONS = tuple(
    _load_registration(name, builtin=name.startswith("ebm.tiles.builtin."))
    for name in discover_tile_modules()
)
_BY_ID = {registration.id: registration for registration in _REGISTRATIONS}
if len(_BY_ID) != len(_REGISTRATIONS):
    raise ValueError("duplicate generated tile id in catalog")


def all_tiles() -> tuple[TileRegistration, ...]:
    return _REGISTRATIONS


def active_tiles() -> tuple[TileRegistration, ...]:
    return tuple(registration for registration in _REGISTRATIONS if registration.enabled)


def get_tile(tile_id: str) -> TileRegistration:
    try:
        return _BY_ID[tile_id]
    except KeyError:
        raise KeyError(f"unknown tile id: {tile_id}") from None


def create_tile(tile_id: str) -> TileBase:
    return get_tile(tile_id).create()


def default_tile() -> TileBase:
    return create_tile("builtin.powered-channel")
