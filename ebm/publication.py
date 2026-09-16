"""Deterministic publication checks: each enabled tile, never random mixtures."""
from __future__ import annotations

from .repeat_validation import validate_repeated_flow
from .tile_catalog import all_tiles
from .validator import validate_tile_flow


def validate_publication(registrations=None):
    registrations = all_tiles() if registrations is None else tuple(registrations)
    if not any(tile.enabled for tile in registrations):
        return {"ok": False, "error": "No enabled tiles: enable at least one tile before publishing", "tiles": []}
    results = []
    for tile in registrations:
        if not tile.enabled:
            results.append({"id": tile.id, "enabled": False, "status": "skipped"})
            continue
        single = validate_tile_flow(tile.create, name=tile.title)
        repeat = validate_repeated_flow(tile.create)
        results.append({
            "id": tile.id, "enabled": True,
            "status": "passed" if single.ok and repeat.ok else "failed",
            "single": single.to_dict(), "repeat": repeat.to_dict(),
        })
    return {"ok": all(tile["status"] != "failed" for tile in results), "tiles": results}
