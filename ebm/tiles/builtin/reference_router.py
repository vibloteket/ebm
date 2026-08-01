from ebm.tiles.builtin.powered_channel import PoweredChannelTile


class ReferenceRouterTile(PoweredChannelTile):
    """Legacy catalog example retained as a route-free flow tile."""

    id = "ebm.reference-router"
    title = "Reference Distributor"


TILE_CLASS = ReferenceRouterTile
