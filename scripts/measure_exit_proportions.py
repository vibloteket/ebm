"""Measure per-tile exit proportions with the standard flow validator.

Runs validate_tile_flow on every registered tile and reports the B0/R0
split so we can decide on a min_output_share threshold.
"""
import json
import sys
import time

from ebm.tile_catalog import all_tiles
from ebm.validator import validate_tile_flow


def main() -> int:
    rows = []
    for registration in all_tiles():
        tile_id = registration.id
        started = time.perf_counter()
        try:
            result = validate_tile_flow(registration.create, name=tile_id)
        except Exception as error:  # pragma: no cover - defensive
            rows.append({"tile": tile_id, "error": f"{type(error).__name__}: {error}"})
            print(f"{tile_id:35s} ERROR {type(error).__name__}: {error}", flush=True)
            continue
        elapsed = time.perf_counter() - started
        counts = result.output_counts
        exited = result.exited
        shares = {port: (count / exited if exited else 0.0) for port, count in counts.items()}
        rows.append(
            {
                "tile": tile_id,
                "enabled": registration.enabled,
                "ok": result.ok,
                "spawned": result.balls_spawned,
                "exited": exited,
                "active": result.active,
                "invalid": result.invalid,
                "lost": result.lost,
                "output_counts": counts,
                "shares": {k: round(v, 4) for k, v in shares.items()},
                "seconds": round(elapsed, 2),
            }
        )
        share_txt = "  ".join(f"{p}={c:3d} ({shares[p] * 100:5.1f}%)" for p, c in counts.items())
        status = "ok " if result.ok else "FAIL"
        print(
            f"{tile_id:35s} {status} exited={exited:3d} active={result.active:2d} "
            f"invalid={result.invalid} lost={result.lost}  {share_txt}  [{elapsed:4.1f}s]",
            flush=True,
        )
    print("\nJSON:")
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
