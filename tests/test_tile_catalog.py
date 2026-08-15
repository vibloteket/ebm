import pytest

from ebm.tile_catalog import all_tiles, create_tile, default_tile, get_tile
from ebm.tiles import PoweredChannelTile


def test_catalog_exposes_independent_builtin_modules():
    registrations = all_tiles()
    assert {item.id for item in registrations} == {
        "builtin.powered-channel",
        "builtin.reference-router",
        "contributed.segment-switchback",
        "contributed.teleport-collector",
    }
    assert {item.title for item in registrations} == {
        "Powered Channel Tile",
        "Reference Router Tile",
        "Segment Switchback",
        "Teleport Collector",
    }
    assert not get_tile("contributed.segment-switchback").builtin


def test_catalog_creates_route_free_tiles():
    assert isinstance(default_tile(), PoweredChannelTile)
    assert isinstance(create_tile("builtin.powered-channel"), PoweredChannelTile)
    assert not hasattr(default_tile(), "route")


def test_catalog_rejects_unknown_id():
    with pytest.raises(KeyError):
        get_tile("missing.tile")
