from __future__ import annotations

from ebm import TileBase, TileBuilder


RAIL = (35, 104, 176, 255)
GATE = (238, 147, 31, 255)
PIVOT = (92, 54, 22, 255)


class MirroredSSwitch(TileBase):
    """Passive gravity chutes with a freely pivoting physical switch."""

    author = "Pi"

    def build(self, b: TileBuilder) -> None:
        # The upper and left arrivals are caught by passive rails. The two
        # routes cross through the middle in a compact mirrored-S layout.
        # Keep exit speed without extending the supporting rail into R0's
        # neighbour. The final section slopes gently down inside the tile.
        _rail(b, (120, 85), (300, 350), friction=0)
        _rail(b, (300, 350), (395, 355), friction=0)
        _rail(b, (260, 20), (385, 205))
        _rail(b, (385, 205), (395, 205 + 10 * 45 / 35))

        _rail(b, (5, 180 + 25 * 50 / 105), (85, 230))
        _rail(b, (85, 230), (145, 350))
        _rail(b, (145, 350), (145, 395))
        _rail(b, (65, 50), (115, 155))
        _rail(b, (115, 155), (255, 335))
        _rail(b, (255, 335), (255, 395))

        # A visible, unpowered cross pivots freely in the shared centre. It
        # moves only from physical contacts; it has no sensor or callback.
        rotor = b.dynamic_body((205, 260), angle=0.35)
        for a, end in (((-22, 0), (22, 0)), ((0, -22), (0, 22))):
            b.segment_shape(
                rotor, a, end, 4,
                density=0.06,
                friction=0.15,
                elasticity=0.3,
                fill_color=GATE,
            )
        b.circle_shape(
            rotor, (0, 0), 6,
            density=0.06,
            friction=0.15,
            elasticity=0.2,
            fill_color=PIVOT,
        )
        b.pivot(rotor, (205, 260))


def _rail(b: TileBuilder, a, end, *, friction=0.15):
    return b.static_segment(
        a,
        end,
        5,
        friction=friction,
        elasticity=0.45,
        fill_color=RAIL,
    )
