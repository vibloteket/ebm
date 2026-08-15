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
        _rail(b, (120, 85), (300, 350))
        _rail(b, (300, 350), (420, 350))
        _rail(b, (260, 20), (385, 205))
        _rail(b, (385, 205), (420, 250))

        # L0 -> B0: the lower rail catches the complete L0 opening without
        # blocking it, then gravity carries the ball into a vertical throat.
        _rail(b, (-20, 180), (85, 230))
        _rail(b, (85, 230), (145, 350))
        _rail(b, (145, 350), (145, 420))
        _rail(b, (65, 65), (115, 155))
        _rail(b, (115, 155), (255, 335))
        _rail(b, (255, 335), (255, 420))


def _rail(b: TileBuilder, a, end) -> None:
    b.static_segment(
        a,
        end,
        5,
        friction=0.15,
        elasticity=RAIL_ELASTICITY,
        fill_color=RAIL,
    )
