# Endless Ball Machine — Implementation Plan

Endless Ball Machine (EBM) is a browser-based, community-built ball machine inspired by the classic Blue Ball Machine. It runs real-time physics with Python + pymunk in the browser, uses an effectively infinite pan-only canvas, and lets contributors add new machine tiles through pull requests.

- **Repo name:** `endless-ball-machine`
- **Python package / CLI shorthand:** `ebm`
- **Core idea:** an endless grid of 200×200 physics tiles, with procedural filler tiles everywhere no contributed tile exists.

## Goals

1. Run real pymunk physics client-side in the browser.
2. Let viewers pan around an endless machine.
3. Let viewers interact by dropping balls into the simulation.
4. Let contributors add tiles with a single Python file.
5. Keep the original BBM feel: visually seamless, not obviously boxed into cells.
6. Keep contribution rules simple enough that people can make PRs easily.

## Non-goals / deferred ideas

- No server-side simulation.
- No zoom initially; fixed scale preserves the endless-canvas feel and keeps performance stable.
- No image assets in contributed tiles.
- No visible connector/funnel geometry at tile borders.
- No separate repo for tiles; use one repo with protected core directories.
- No complex global graph solver in v1. Start with a simple deterministic route-contract field.

## Browser/runtime architecture

### Pyodide + pymunk

Use Pyodide to run Python in the browser. Pymunk already publishes WASM-compatible wheels, so the intended deployment is fully static and can run on GitHub Pages or another static host.

### One shared physics space

Use one active `pymunk.Space`, not one space per tile. Tiles contribute geometry to the shared space, and balls move across tile boundaries naturally.

```python
space = pymunk.Space()
space.gravity = (0, 900)
```

There is no explicit ball handoff between tiles. The physics world itself is the interface.

### Infinite canvas via active-window loading

The canvas is conceptually infinite, but only a moving window of tiles is loaded:

- Viewport example: ~1200×800px = about 6×4 visible tiles.
- Active zone: viewport plus ~2 tile buffer on all sides = about 10×8 = ~80 active tiles.
- As the viewer pans, load newly needed border tiles and unload tiles that leave the active zone.
- Recompute active tiles only when the viewport crosses a tile boundary, not on every pixel of movement.

This keeps performance bounded regardless of how large the world appears.

### Ball lifecycle

- Maintain a target number of balls in the active zone, e.g. ~40.
- Balls that leave the active zone are despawned.
- New balls are spawned near the top of the active zone/viewport to keep the machine alive.
- Viewer clicks/taps spawn extra balls at that world position.

Tile state is only active while the tile is loaded. If a viewer pans away, the tile is unloaded and its local state resets when loaded again. This is acceptable for v1.

### Precision

Chipmunk/pymunk use double precision. Floating point precision is not a practical issue until absurd distances from the origin, roughly on the order of `1e14` pixels. At normal pan speeds this is thousands of years of travel, so no floating-origin system is needed initially.

## Navigation and UI

- Pan with drag and/or keyboard.
- Click/tap to drop a ball.
- Hover/tap a tile to show coordinate, title, and author.
- Optional minimap: dots for contributed tiles and a marker for the current viewport.
- No zoom at first.
- Tile grid lines should be absent or very subtle; the machine should not look like obvious boxed cells.

## Rendering

Use Canvas2D first. It is simpler than WebGL and should be enough for the expected active object count.

Render common pymunk shapes:

- `pymunk.Segment` as stroked lines with `lineWidth = radius * 2`.
- `pymunk.Circle` as arcs/circles.
- `pymunk.Poly` as filled/stroked paths.
- Balls as blue circles.
- Allow `shape.color` or similar metadata for custom tile colors.

Suggested style:

- Dark background.
- Blue/teal geometry.
- Bright blue balls.
- Optional subtle glow/shadow.
- Contributed tiles may be visually a little richer than filler tiles, but avoid heavy outlines that reveal the grid too strongly.

## Tile model

### Terminology

Use **tile**, not cell. The project is an endless grid of tiles.

### Tile size

Each tile is exactly `200×200` world pixels.

```python
TILE_SIZE = 200
```

### Ghost ports

Every tile has six fixed ghost ports. They are just documented coordinates, not rendered connectors and not physical funnels. The v1 port model follows the original-BBM-like pattern: one top input, one bottom output, and side ports that are input on the upper side and output on the lower side.

```text
                  T0 input (100, 0)
                         ↓
        ┌────────────────●────────────────┐
        │                                 │
L0 in → ●                                 ● → R1 out
 (0,50)│                                 │  (200,50)
        │             200 × 200           │
L1 out← ●                                 ● ← R0 in
(0,150)│                                 │  (200,150)
        └────────────────●────────────────┘
                         ↓
                 B0 output (100, 200)
```

Input ports:

- `T0` at `(100, 0)`
- `L0` at `(0, 50)`
- `R0` at `(200, 150)`

Output ports:

- `B0` at `(100, 200)`
- `L1` at `(0, 150)`
- `R1` at `(200, 50)`

Mirror relationships across tile boundaries:

- `B0 ↔ T0`
- `R1 ↔ L0`
- `L1 ↔ R0`

Ports are a contract for authors and tooling. A tile should guide balls from its declared entries to its declared exits, but nothing should be physically forced at the tile boundary.

### Entries and exits

Each tile declares lists of entries and exits:

```python
entries = [Port.T0]
exits = [Port.B0]
```

Rules:

1. `len(entries) == len(exits)`.
2. `entries` may only contain input ports: `T0`, `L0`, `R0`.
3. `exits` may only contain output ports: `B0`, `L1`, `R1`.
4. A port may appear at most once in `entries`.
5. A port may appear at most once in `exits`.
6. A tile does **not** declare exact entry-to-exit pairing. It declares which ports it consumes from and which ports it emits to.
7. A normal stream of balls entering through declared entries should eventually leave through declared exits.

This supports simple tiles, crossings, pass-throughs, buckets, switchers, and mixers. Example crossing-style declaration:

```python
entries = [Port.T0, Port.L0]
exits = [Port.B0, Port.R1]
```

A tile may collect multiple balls, use bucket/seesaw/counter mechanics, then release them later. The requirement is eventual throughput, not immediate one-in/one-out behavior.

## Tile author API

Do **not** expose raw `pymunk.Space` as the normal authoring API. Tile authors build through a tile-local context so they cannot forget to offset coordinates by tile origin and so the engine can track objects for unloading.

### Minimal tile file

```python
from ebm import TileBase, Port

class Tile(TileBase):
    author = "github-username"
    title = "Simple Ramp"

    # None means standalone/auto. Set both to ints for exact placement.
    row = None
    col = None

    entries = [Port.T0]
    exits = [Port.B0]

    def build(self, ctx):
        ramp = ctx.segment((100, 10), (100, 190), radius=3)
        ramp.friction = 0.7
        ramp.elasticity = 0.3

    def update(self, ctx, dt):
        # Optional: animate kinematic bodies, motors, etc.
        pass

    def destroy(self, ctx):
        # Optional cleanup. Usually unnecessary.
        pass
```

All coordinates passed to `ctx` helpers are tile-local unless explicitly documented otherwise.

### Suggested `TileContext` API

Minimal v1 helpers:

```python
ctx.segment(a, b, radius=1, body=None)
ctx.circle(position, radius, body=None)
ctx.poly(points, body=None)

ctx.dynamic_body(position, mass, moment=None)
ctx.kinematic_body(position)
ctx.static_body(position=None)

ctx.pivot_to_static(body, anchor=None)
ctx.pivot(body_a, body_b, anchor_a=None, anchor_b=None)
ctx.motor(body_a, body_b, rate)

ctx.point(x, y)  # convert tile-local point to world point; mainly for update()
```

The context adds objects to the underlying `pymunk.Space` and records them so the engine can remove them when the tile unloads.

Collision callbacks can be added later through controlled helpers, for example:

```python
sensor = ctx.sensor_circle((100, 100), radius=20)
ctx.on_ball_hit(sensor, self.on_ball_hit)
```

Avoid exposing raw `space` in v1. Add an advanced escape hatch only if the helper API proves too restrictive.

### Tile author rules

Short version for contributors:

1. One tile = one `.py` file in `tiles/`.
2. Define a `Tile` class.
3. All geometry must stay inside the tile's 200×200 bounds.
4. Declare `entries` and `exits`; the lists must have the same length.
5. A normal stream of balls entering at declared entries should eventually leave near declared exits.
6. Multi-ball mechanisms are allowed and encouraged; do not permanently trap balls.
7. Keep tile complexity bounded, initially max ~30 shapes.
8. No image files/assets. Use code-drawn geometry.
9. Avoid extreme elasticity or motors that launch balls uncontrollably unless intentional and reviewable.
10. Stray balls from unexpected directions should ideally fall through or bounce out eventually.

## Route contracts / global flow

### v1 decision: use the easier route-field approach

Do **not** start with a full global graph solver. Instead, generate a deterministic route-contract field. Each coordinate has a contract:

```python
required_entries = [...]
required_exits = [...]
```

Then the system chooses a tile that matches that contract:

1. Explicit contributed tile at that coordinate, if present.
2. Canonical auto/standalone contributed tile placed there by generated layout, if present.
3. Deterministic reused standalone contributed tile matching the contract, if available.
4. Procedural filler tile matching the contract.

The route owns the ports. Tiles implement the ports.

### Base route field

For v1, use a simple deterministic row-lane field that generally flows downward and only emits route contracts the filler system supports. This is intentionally a placeholder that can be tuned once the prototype runs.

Supported v1 contracts:

- All 9 single-flow contracts from one input port to one output port:
  - `T0 -> B0`, `T0 -> L1`, `T0 -> R1`
  - `L0 -> B0`, `L0 -> L1`, `L0 -> R1`
  - `R0 -> B0`, `R0 -> L1`, `R0 -> R1`
- 3 common double-flow contracts:
  - `[T0, L0] -> [B0, R1]`  — vertical plus left-to-right
  - `[T0, R0] -> [B0, L1]`  — vertical plus right-to-left
  - `[L0, R0] -> [L1, R1]`  — side streams

Initial route-field shape:

- Default contract is `[T0] -> [B0]`.
- Some rows contain deterministic horizontal lane segments.
- A lane has a direction, a start column, and a length.
- Lane start turns vertical flow sideways: e.g. `[T0] -> [R1]`.
- Lane middle passes side-to-side: e.g. `[L0] -> [R1]`.
- Lane end turns side flow downward: e.g. `[L0] -> [B0]`.
- Occasional middle cells use double-flow crossing contracts to preserve vertical flow while a side lane passes through.

Initial tuning constants:

```python
LANE_ROW_PROBABILITY = 0.20
LANE_MIN_LENGTH = 3
LANE_MAX_LENGTH = 7
CROSSING_PROBABILITY = 0.30
```

These values are not important yet; pick something simple and tune after there is a running prototype.

### Explicit tiles as constraints

A tile with explicit `row`/`col` overrides the base route contract at that coordinate.

Neighboring generated/filler tiles should adapt locally to satisfy explicit tile entries/exits where possible. If explicit placements create direct port mismatches or impossible local constraints, validation fails or warns strongly.

Direct connection rule:

- If tile A exits through a side into tile B, tile B must include the mirrored port in its `entries`.
- If tile A expects entry from tile B, tile B must include the mirrored port in its `exits`.

For v1, avoid advanced graph validation. Hard-fail obvious direct conflicts; warn on suspicious closed loops or unreachable patterns.

## Tile placement and reuse

### Two placement modes

#### Standalone/auto tiles

If `row = None` and `col = None`, the tile is a standalone contribution.

Standalone tiles:

1. Get one canonical placement near the origin in generated layout.
2. May also be reused elsewhere in the endless procedural field whenever their `entries`/`exits` exactly match the local route contract.

This keeps far-away panning interesting even when the project has few contributions.

#### Explicit/landmark tiles

If both `row` and `col` are integers, the tile is placed at that exact grid coordinate.

Explicit tiles:

1. Appear only at their declared coordinate.
2. Are never reused automatically.
3. Enable advanced authors to build multi-tile compositions by placing several files adjacent to each other.

No separate `group` metadata is needed; adjacency is the grouping.

Do not allow only one of `row`/`col` to be set.

### Generated layout

At build/deploy time:

1. Load all contributed tile classes.
2. Place explicit-coordinate tiles first.
3. Validate duplicate coordinates and obvious direct port conflicts.
4. Generate a deterministic route field around the origin.
5. Place each standalone tile once at a nearby coordinate whose route contract matches its `entries`/`exits`.
6. Save generated layout data for the browser.

Runtime lookup:

```python
def get_tile_at(coord):
    if coord in explicit_layout:
        return explicit_layout[coord]
    if coord in canonical_standalone_layout:
        return canonical_standalone_layout[coord]

    contract = route_contract_at(coord)
    contributed = choose_repeatable_contributed_tile(contract, coord)
    if contributed:
        return contributed

    return generate_filler(contract, coord)
```

Generate `TILEMAP.md` from explicit and canonical placements so contributors can find open coordinates and see where their tile lives.

## Filler tiles

Every unclaimed coordinate is filled by a deterministic procedural filler tile matching the route contract at that coordinate.

### Filler requirements

- Deterministic by coordinate and `WORLD_SEED`.
- Cheap to build/render.
- Reliable enough that balls generally keep moving.
- Visually simple compared to contributed tiles.
- Must support every route contract emitted by the v1 route field.

### Stable randomness

Do not use Python's built-in `hash()` for world generation. It is not stable across runs. Use a stable hash:

```python
import hashlib
import random

def stable_seed(row, col, world_seed):
    data = f"{world_seed}:{row}:{col}".encode()
    return int.from_bytes(hashlib.sha256(data).digest()[:8], "big")

rng = random.Random(stable_seed(row, col, WORLD_SEED))
```

### Filler generation

For v1, fillers should be as simple as possible. Goal #1 is to get a working browser simulation; visual variety comes later.

Implement:

- A generic single-flow filler for all 9 single-flow contracts.
- Simple handwritten fillers for the 3 supported double-flow contracts.

The generic filler can draw a straightforward descending rail/ramp/polyline between the entry point and exit point. Double-flow fillers can internally pair ports however is convenient, for example `[T0, L0] -> [B0, R1]` can be implemented as `T0 -> B0` plus `L0 -> R1`. This pairing is a filler implementation detail, not part of the public tile API.

The route field must not emit a contract unless the filler system can produce it.

Later, add variations per contract:

- zigzags
- bumpers
- halfpipes
- wheels
- spring pads
- funnels
- pendulums

But first filler should be reliable plumbing.

## Validation and CI

CI should keep the project safe but not over-police creative physics. Some checks are hard failures; flow checks can be advisory with a report and preview.

### Hard failures

- Tile file has syntax/import errors.
- No `Tile` class or missing required metadata.
- Invalid `row`/`col` pairing.
- Coordinate conflict.
- Invalid `entries`/`exits` lists.
- Shape/body/constraint count over limits.
- Static geometry outside tile bounds.
- Build method fails at runtime.
- Obvious direct port mismatch between explicit neighboring tiles.

### Suggested limits

```python
MAX_SHAPES_PER_TILE = 30
MAX_BODIES_PER_TILE = 12
MAX_CONSTRAINTS_PER_TILE = 12
```

Tune after the first performance spike.

### Advisory checks

- Drop a stream of balls at each declared entry over a fixed time.
- Count how many leave through any declared exit.
- Run individual-entry tests and combined-all-entries tests.
- Report stuck balls or balls leaving through unexpected ports.
- Do not necessarily fail solely because a tile has imperfect flow; review the GIF.

A bucket tile may intentionally hold balls for several seconds before releasing them, so validation should measure throughput over time rather than expecting each ball to exit quickly.

### Security / import guardrails

Contributed tiles are reviewed Python code, not inert data. They run in CI/local preview and in the browser. Keep the author API constrained.

Start with an import allowlist, for example:

- `math`
- `random`
- `pymunk` if needed indirectly, though most authors should use `ctx`
- `ebm`
- maybe `itertools`, `collections`

Disallow obvious unsafe/unnecessary imports such as `os`, `sys`, `subprocess`, `socket`, `pathlib`, `requests`, `urllib`.

### PR preview

For each changed tile:

- Generate a GIF/video preview of the tile with test balls.
- If a PR adds adjacent explicit-coordinate tiles, also generate a combined preview of that area.
- Post a PR comment with shape/body/constraint counts, bounds status, coordinate status, flow ratio, and preview.

## Local development tools

Provide a CLI through the package shorthand `ebm`.

Examples:

```bash
python -m ebm preview my_tile
python -m ebm run
python -m ebm validate
python -m ebm tilemap
```

### `preview`

Shows one contributed tile in context with procedural neighbors and balls entering from declared entry ports. This can initially use pygame for local development.

### `run`

Runs the full machine locally in a desktop preview with panning and click-to-drop.

### `validate`

Runs the same checks as CI.

### `tilemap`

Regenerates `TILEMAP.md`.

## Repo structure

Single repo, with protected core paths and open contributed tile path.

```text
endless-ball-machine/
├── ebm/
│   ├── __init__.py
│   ├── tile_base.py          # TileBase, Port, constants
│   ├── context.py            # TileContext author API
│   ├── engine.py             # pymunk space, active tile lifecycle, balls
│   ├── routes.py             # route contract generation
│   ├── layout.py             # explicit + canonical standalone placement
│   ├── loader.py             # load tile modules
│   ├── validator.py          # CI/local validation
│   ├── renderer.py           # shared render data/helpers if useful
│   └── fillers/
│       ├── __init__.py
│       ├── ramp.py
│       ├── zigzag.py
│       └── ...
├── tiles/
│   ├── simple_ramp.py
│   └── ...
├── web/
│   ├── index.html
│   ├── main.js               # Pyodide bootstrap + input handling
│   └── style.css
├── tools/
│   └── ...
├── tests/
│   └── test_tiles.py
├── docs/
│   └── IMPLEMENTATION_PLAN.md
├── TILE_GUIDE.md
├── TILEMAP.md                # generated
├── README.md
├── pyproject.toml
└── .github/
    ├── CODEOWNERS
    └── workflows/
        ├── validate.yml
        └── deploy.yml
```

Suggested CODEOWNERS:

```text
/ebm/             @viblo
/web/             @viblo
/tools/           @viblo
/pyproject.toml   @viblo
```

No CODEOWNERS requirement for `tiles/`, so tile PRs can be lightweight while still validated by CI.

## Deployment

Static deployment, ideally GitHub Pages.

On push to main:

1. Run full validation.
2. Compute route/layout data.
3. Generate `TILEMAP.md` and layout data for the browser.
4. Deploy `web/`, `ebm/`, `tiles/`, and generated layout metadata.
5. Browser loads Pyodide, pymunk, engine code, tile files, layout data, and starts simulation.

## Implementation phases

### Phase 1 — Browser physics spike

- Minimal `ebm` package.
- Pyodide bootstrap.
- Pymunk space in browser.
- `TileContext` helpers for basic static geometry.
- Canvas2D renderer.
- A few hardcoded filler/contributed tiles.
- Pan and click-to-drop.

Success criterion: real-time balls roll across several loaded tiles in the browser.

### Phase 2 — Route contracts, tile loading, and layout

- Implement `TileBase`, `Port`, entries/exits validation.
- Implement simple deterministic route field.
- Implement filler generation for supported contracts.
- Load tile Python files dynamically.
- Add explicit placement and canonical standalone placement.

Success criterion: contributed tile files appear in the machine at stable coordinates and repeated standalone tiles appear in matching far-away locations.

### Phase 3 — Local author workflow

- `python -m ebm preview <tile>`.
- `python -m ebm validate`.
- Draft `TILE_GUIDE.md`.
- Seed several example tiles.

Success criterion: a contributor can create and test a tile locally.

### Phase 4 — CI and previews

- GitHub Actions validation.
- GIF/video preview generation.
- PR comment report.
- Generate `TILEMAP.md`.

Success criterion: tile PRs are safe and reviewable.

### Phase 5 — Polish and launch

- Minimap.
- Hover metadata.
- Better visual styling.
- More filler templates.
- 20–30 seed contributed tiles.
- README and launch docs.

## Key constants

```python
TILE_SIZE = 200
WORLD_SEED = 42
TARGET_BALLS = 40
BUFFER_TILES = 2
LANE_ROW_PROBABILITY = 0.20
LANE_MIN_LENGTH = 3
LANE_MAX_LENGTH = 7
CROSSING_PROBABILITY = 0.30
MAX_SHAPES_PER_TILE = 30
MAX_BODIES_PER_TILE = 12
MAX_CONSTRAINTS_PER_TILE = 12
PHYSICS_DT = 1 / 60
BALL_RADIUS = 8
BALL_MASS = 1
BALL_ELASTICITY = 0.6
```

These should be easy to tune after the first browser performance test.
