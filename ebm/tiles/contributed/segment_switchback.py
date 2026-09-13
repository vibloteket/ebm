from __future__ import annotations

from ebm import TileBase, TileBuilder


RAIL = (49, 90, 168, 255)
RAIL_ELASTICITY = 0.45


class SegmentSwitchback(TileBase):
    """Two passive gravity chutes built exclusively from static segments."""

    author = "Pi"

    def build(self, b: TileBuilder) -> None:
        # T0 -> R0: paired rails form a downhill channel. Its final straight
        # section aligns the ball with the right-hand output.
        # Low-friction exit rails retain enough speed to cross R0 within the
        # angle contract after support ends strictly inside this tile.
        _rail(b, (120, 85), (300, 350), friction=0)
        _rail(b, (300, 350), (395, 355), friction=0)
        _rail(b, (260, 20), (385, 205))
        _rail(b, (385, 205), (395, 205 + 10 * 45 / 35))

        # L0 -> B0: the lower rail catches the complete L0 opening without
        # blocking it, then gravity carries the ball into a vertical throat.
        _rail(b, (5, 180 + 25 * 50 / 105), (85, 230))
        _rail(b, (85, 230), (145, 350))
        _rail(b, (145, 350), (145, 395))
        # Raise the lip so high L0 arrivals do not rebound out to the left.
        _rail(b, (65, 50), (115, 155))
        _rail(b, (115, 155), (255, 335))
        _rail(b, (255, 335), (255, 395))


def _rail(b: TileBuilder, a, end, *, friction=0.15) -> None:
    b.static_segment(
        a,
        end,
        5,
        friction=friction,
        elasticity=RAIL_ELASTICITY,
        fill_color=RAIL,
    )
