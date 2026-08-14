from __future__ import annotations

from ebm import TileBase, TileBuilder


RAIL = (49, 90, 168, 255)


class SegmentSwitchback(TileBase):
    """Routes balls with real colliding segment rails and conveyor friction."""

    author = "Pi"

    def build(self, b: TileBuilder) -> None:
        # T0 -> R0: a guarded entrance catches even the widest/slowest
        # validation shots before the descending conveyor turns them right.
        _rail(b, (140, -20), (140, 105), (0, 700))
        _rail(b, (260, -20), (260, 105), (0, 700))
        _rail(b, (105, 105), (345, 255), (620, 390))
        _rail(b, (180, 35), (345, 255), (500, 440))
        _rail(b, (345, 255), (420, 255), (900, 0))
        _rail(b, (345, 345), (420, 345), (900, 0))

        # L0 -> B0: this lower chute catches balls below the upper conveyor and
        # narrows into the bottom aperture under gravity.
        _rail(b, (-20, 165), (115, 175), (500, 40))
        _rail(b, (115, 175), (165, 420), (140, 690))
        _rail(b, (285, 245), (235, 420), (-190, 665))

        # Close only the non-port portions of the bottom and right boundaries.
        _rail(b, (0, 400), (145, 400), (0, 0))
        _rail(b, (255, 400), (400, 400), (0, 0))
        _rail(b, (400, 0), (400, 245), (0, 0))
        _rail(b, (400, 355), (400, 400), (0, 0))


def _rail(b: TileBuilder, a, end, velocity) -> None:
    b.static_segment(
        a,
        end,
        6,
        friction=1.0,
        elasticity=0.02,
        surface_velocity=velocity,
        fill_color=RAIL,
    )
