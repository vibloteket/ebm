import pytest

from ebm.tile_catalog import all_tiles, create_tile, default_tile, discover_tile_modules, get_tile
from ebm.tile_base import tile_display_name
from ebm.tiles import PoweredChannelTile


def test_catalog_exposes_independent_builtin_modules():
    registrations = all_tiles()
    assert tuple(item.module for item in registrations) == discover_tile_modules()
    assert len({item.id for item in registrations}) == len(registrations)
    for item in registrations:
        assert item.title == tile_display_name(item.tile_class)
        assert item.builtin == item.module.startswith("ebm.tiles.builtin.")
        assert type(item.enabled) is bool


def test_catalog_creates_route_free_tiles():
    assert isinstance(default_tile(), PoweredChannelTile)
    assert isinstance(create_tile("builtin.powered-channel"), PoweredChannelTile)
    assert not hasattr(default_tile(), "route")


def test_catalog_rejects_unknown_id():
    with pytest.raises(KeyError):
        get_tile("missing.tile")
