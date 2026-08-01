#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/dist/site}"

rm -rf "$OUT"
mkdir -p "$OUT/ebm"

cp "$ROOT/web/index.html" "$OUT/index.html"
cp "$ROOT/web/admin.html" "$OUT/admin.html"
cp "$ROOT/web/map-debug.html" "$OUT/map-debug.html"
cp "$ROOT/web/map-debug.js" "$OUT/map-debug.js"
cp "$ROOT/web/map-debug.css" "$OUT/map-debug.css"
cp "$ROOT/web/map-data.json" "$OUT/map-data.json"
cp "$ROOT/web/main.js" "$OUT/main.js"
cp "$ROOT/web/v3-renderer.js" "$OUT/v3-renderer.js"
cp "$ROOT/web/debug.html" "$OUT/debug.html"
cp "$ROOT/web/debug.js" "$OUT/debug.js"
cp "$ROOT/web/editor.html" "$OUT/editor.html"
cp "$ROOT/web/editor.js" "$OUT/editor.js"
cp "$ROOT/web/api-reference.js" "$OUT/api-reference.js"
cp "$ROOT/web/editor.css" "$OUT/editor.css"
python "$ROOT/scripts/generate_api_reference.py" "$OUT/api-reference.json"
cp "$ROOT/web/compare.html" "$OUT/compare.html"
cp "$ROOT/web/compare.js" "$OUT/compare.js"
cp "$ROOT/web/compare.css" "$OUT/compare.css"
cp "$ROOT/web/style.css" "$OUT/style.css"
if [ -d "$ROOT/web/vendor" ]; then
  cp -a "$ROOT/web/vendor" "$OUT/vendor"
fi

# The browser loads this package into Pyodide. Preserve tile subpackages so
# each tile remains an independently fetchable source module for the editor.
find "$ROOT/ebm" -type f -name '*.py' -print0 | while IFS= read -r -d '' source; do
  relative="${source#$ROOT/}"
  mkdir -p "$OUT/$(dirname "$relative")"
  cp "$source" "$OUT/$relative"
done

python - "$ROOT" "$OUT" <<'PY'
import json
import sys
from pathlib import Path

root, out = map(Path, sys.argv[1:])
sys.path.insert(0, str(root))
from ebm.tile_catalog import all_tiles

manifest = {"apiVersion": 2, "tiles": []}
source_dir = out / "tiles" / "sources"
source_dir.mkdir(parents=True, exist_ok=True)
for registration in all_tiles():
    cls = registration.tile_class
    relative = Path(*registration.module.split(".")).with_suffix(".py")
    source_name = f"{cls.id}.py"
    (source_dir / source_name).write_text((root / relative).read_text())
    manifest["tiles"].append({
        "id": cls.id,
        "title": cls.title,
        "author": cls.author,
        "apiVersion": cls.api_version,
        "module": registration.module,
        "class": cls.__name__,
        "source": f"tiles/sources/{source_name}",
        "builtin": registration.builtin,
    })
(out / "tiles" / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
PY

cat > "$OUT/README.txt" <<'TXT'
Endless Ball Machine static site

This directory is self-contained except for CDN/PyPI downloads used by Pyodide:
- Pyodide from cdn.jsdelivr.net
- pymunk installed in-browser via micropip
TXT

echo "Built static site at $OUT"
