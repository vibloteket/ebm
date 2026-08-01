import pytest

from ebm.routes import ALL_ROUTES, DEFAULT_ROUTES
from ebm.tile_catalog import all_tiles, candidates_for, create_tile, get_tile, tile_for_route
from ebm.tiles import PoweredChannelTile, ReferenceRouterTile


def test_catalog_exposes_independent_builtin_modules():
    registrations = all_tiles()
    assert {item.id for item in registrations} == {
        "ebm.powered-channel",
        "ebm.reference-router",
    }
    assert {item.module for item in registrations} == {
        "ebm.tiles.builtin.powered_channel",
        "ebm.tiles.builtin.reference_router",
    }


def test_catalog_selects_powered_defaults_and_reference_fallbacks():
    assert isinstance(tile_for_route(DEFAULT_ROUTES[0]), PoweredChannelTile)
    fallback = next(route for route in ALL_ROUTES if route not in DEFAULT_ROUTES)
    assert isinstance(tile_for_route(fallback), ReferenceRouterTile)
    assert {item.id for item in candidates_for(fallback)} == {"ebm.reference-router"}


def test_catalog_validates_id_and_supported_routes():
    route = DEFAULT_ROUTES[0]
    assert isinstance(create_tile("ebm.powered-channel", route), PoweredChannelTile)
    assert get_tile("ebm.powered-channel").tile_class.routes == DEFAULT_ROUTES
    unsupported = next(item for item in ALL_ROUTES if item not in DEFAULT_ROUTES)
    with pytest.raises(ValueError):
        create_tile("ebm.powered-channel", unsupported)
    with pytest.raises(KeyError):
        get_tile("missing.tile")
