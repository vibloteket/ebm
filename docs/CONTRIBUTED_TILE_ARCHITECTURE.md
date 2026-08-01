# Contributed Tile Architecture

Status: implemented foundation; uniform routing, capability API, and six reference routes active

## Decision summary

Endless Ball Machine will continue to use **one shared Pymunk `Space`** for all active tiles and balls. This preserves continuous contact solving across tile boundaries and avoids the complexity and instability of synchronizing bodies across separate spaces.

Tiles will not receive direct access to the shared `Space`. They will construct and control local physical components through an engine-owned, capability-oriented API.

Contributed tiles may be ordinary reviewed Python code. The browser already provides the practical runtime boundary, and contributions will arrive through pull requests. The goal is therefore not a hostile-code sandbox. The goals are:

- accidental isolation between tiles;
- clear resource ownership and cleanup;
- deterministic, local construction;
- strict behavioral and performance validation;
- an automated path from a green PR to merge.

A malicious tile could still hang its browser tab. That risk is acceptable under the PR and CI review model.

## Why not one `Space` per tile?

A previous prototype idea used one Pymunk space per tile, with an authoritative ball in the space it overlapped most and a ghost ball in the neighboring space. The two bodies would be coupled manually.

This remains an interesting research idea, but is not the chosen EBM architecture. It would require a custom cross-space constraint solver to reconcile:

- position and rotation;
- linear and angular velocity;
- simultaneous contacts on both sides of a boundary;
- friction, restitution, and penetration correction;
- ownership transfer timing;
- contact impulses without duplication or energy loss.

Stacks, large mechanisms, ropes, and objects spanning boundaries would make this substantially harder. One shared solver is both simpler and more physically coherent.

## Core architecture

```text
Contributed tile code
        |
        v
TileBuilder / TileRuntime API
        |
        v
Engine-owned resource registry
        |
        v
One shared Pymunk Space
```

The tile API exposes local construction and owned handles. It does not expose raw global collections or `Space` operations.

## Tile API direction

A future API may resemble:

```python
class TileBuilder:
    def static_segment(self, a, b, radius, material) -> ShapeHandle: ...
    def static_circle(self, center, radius, material) -> ShapeHandle: ...
    def static_polygon(self, points, material) -> ShapeHandle: ...

    def dynamic_body(self, spec: BodySpec) -> BodyHandle: ...
    def circle_shape(self, body, radius, material) -> ShapeHandle: ...
    def segment_shape(self, body, a, b, radius, material) -> ShapeHandle: ...
    def polygon_shape(self, body, points, material) -> ShapeHandle: ...

    def pivot(self, body, anchor) -> ConstraintHandle: ...
    def motor(self, body, rate, max_force) -> ConstraintHandle: ...
    def spring(self, body_a, body_b, spec) -> ConstraintHandle: ...

    def on_ball_contact(self, shape, callback) -> ContactHandle: ...
    def remove(self, owned_handle) -> None: ...
```

Names and signatures are provisional.

### Opaque owned handles

Tile authors receive handles rather than raw `pymunk.Shape`, `Body`, `Constraint`, or `Space` objects.

The engine maintains:

```text
handle -> tile instance -> underlying Pymunk resource
```

Every mutation verifies ownership. A tile can modify or remove its own resources, but cannot enumerate, mutate, or remove resources owned by other tiles.

### Tile-local coordinates

All tile-authored geometry uses local coordinates in the nominal range:

```text
(0, 0) -------- (200, 0)
  |                 |
  |      tile       |
  |                 |
(0, 200) ------ (200, 200)
```

The engine translates local coordinates to world coordinates.

A small engine-defined construction margin may be allowed, for example `-10..210`, so neighboring port geometry can meet cleanly. This margin is policy, not controlled by each tile.

Validation must reject geometry whose full bounding box, including thickness or radius, exceeds the allowed bounds.

## Physics-first behavior

A tile should normally implement only `build()`.

Passive and continuously powered behavior should use Pymunk primitives:

- segments, ramps, walls, funnels, and bumpers;
- friction and elasticity;
- conveyor surfaces via `surface_velocity`;
- dynamic or kinematic bodies;
- pivots, springs, gears, and motors.

Tiles should not poll all balls or bodies. Pymunk should discover contacts through its broadphase and solve them through its normal contact and constraint solver.

The current global body loops in `ebm/fillers.py` are prototype routing hacks and should eventually be removed rather than optimized. They currently inspect `ctx.space.bodies`, set ball velocities, and sometimes reposition balls directly. They are both expensive and insufficiently isolated.

An optional time-based `update(dt)` may remain for genuine mechanism state machines, but it must not provide global body enumeration and its cost must be validated.

## Contact callbacks

Tile authors should not allocate global Pymunk collision IDs.

The engine should install central handlers and associate each shape with ownership metadata. A contact is dispatched to the tile that owns the contacted shape:

```text
Pymunk contact
    -> engine collision dispatcher
    -> owning tile and local ShapeHandle
    -> tile callback
```

A callback receives a restricted contact event rather than the raw `Space` or unrestricted arbiter:

```python
@dataclass(frozen=True)
class ContactEvent:
    own_shape: ShapeHandle
    ball: BallContactHandle
    point: Vec2
    normal: Vec2
    relative_velocity: Vec2
```

The exact callback surface remains to be designed. It should permit useful operations such as triggering a motor, opening a gate, or applying a bounded impulse to the ball involved in that contact.

Callbacks should be reserved for event-driven behavior. Declarative physical materials and constraints are preferred.

## Resource arena and lifecycle

Each activated tile instance owns an engine-managed resource arena containing:

- bodies;
- shapes;
- constraints;
- collision subscriptions;
- visual primitives and cached assets;
- persistent tile state.

Suggested lifecycle:

```python
instance = engine.activate(tile_definition, row, col)
instance.build()
instance.sleep()
instance.wake()
instance.destroy()
```

On destruction, the engine removes all registered resources automatically. Correct cleanup must not depend on contributor code remembering every object.

## Contribution model

Contributed tiles may be normal Python classes, for example:

```python
class WaterWheelTile:
    id = "contributor.water-wheel"
    version = 1
    contract = Contract(entries=[Port.T0], exits=[Port.B0])
    title = "Water Wheel"
    author = "Contributor"

    def build(self, tile):
        wheel = tile.dynamic_body(...)
        tile.circle_shape(wheel, ...)
        tile.pivot(wheel, anchor=(100, 100))
        tile.motor(wheel, rate=1.5, max_force=4_000)
```

Contributions will arrive through pull requests. Review is expected to be largely automated once the API and validator are mature. A tile that passes all mandatory checks should generally be mergeable with minimal manual review.

Absolute security is not a goal. Simple source policy checks still help prevent mistakes and preserve portability. Tile modules should not import `pymunk` directly or access browser, OS, or engine internals.

## Validation pipeline

The existing port-contract validator is the starting point. A contributed-tile validator should eventually include all sections below and produce a machine-readable result.

### 1. Metadata

Required checks:

- unique, stable tile ID;
- supported API version;
- valid title and author metadata;
- valid declared entry and exit ports;
- deterministic construction from a supplied seed.

### 2. Build and bounds

Build the tile and verify:

- all geometry lies within the permitted local bounds and margin;
- all resources belong to the tile instance;
- all numeric values are finite;
- masses, moments, radii, friction, elasticity, forces, and velocities are reasonable;
- resource counts stay within budget;
- construction completes within a timeout.

Initial resource budgets may include limits such as:

```text
Static shapes:      64
Dynamic bodies:     16
Constraints:        24
Contact callbacks:  16
Visual primitives: 128
```

Exact values should be based on profiling and may change.

### 3. Port-contract behavior

Extend today's validator to exercise:

- the full entry-position specification;
- velocity and angle variation;
- every declared entry;
- single and simultaneous balls;
- different ball spacing;
- multiple deterministic seeds;
- long-duration runs.

Required outcomes:

- balls leave through declared exits only;
- exit position remains within the port specification;
- velocity points outward and stays within limits;
- no out-of-bounds escape;
- no stuck or unexpectedly active balls at timeout;
- no NaN state or energy explosion.

### 4. Neighbor compatibility

Test the contribution between standardized reference tiles:

```text
reference producer -> contributed tile -> reference consumer
```

This catches blocked boundaries, overlapping geometry, invalid exit conditions, and balls that pass the isolated test but immediately fail in the next tile.

### 5. Isolation and cleanup

Run the tile among canary neighbors and verify:

- no foreign resource changes;
- no global gravity or solver changes;
- no foreign shape or body removal;
- no contributor-managed global collision IDs;
- all resource counts return to baseline after destruction;
- callbacks and renderer resources are removed.

The API should make most violations impossible, but tests protect against engine regressions.

### 6. Performance and scaling

Measure:

- build time;
- average and maximum `update()` time, when present;
- callback count and cost;
- Pymunk step cost;
- body, shape, and constraint counts;
- rendering and cache cost.

Test both an isolated tile and a grid of repeated copies, such as:

```text
10 x 10 copies
40 balls
12 simulated seconds
```

CI timing varies by host, so use a combination of:

- hard resource limits;
- global timeout;
- comparison with a reference tile in the same run;
- generous relative performance thresholds.

### 7. Determinism

Build and run the same tile twice with the same seed. Compare:

- constructed resource descriptions;
- initial parameters;
- declared behavior and exits;
- rounded trajectories or aggregate outcomes where useful.

Bit-identical Pymunk trajectories across all platforms are not required, but construction and coarse behavior should be reproducible.

### 8. Browser smoke test

Native Python/Pymunk should perform most validation quickly. CI should also run a short browser scenario, preferably in Chromium and Firefox:

- load Pyodide;
- import the tile module;
- build and simulate it;
- verify no console errors;
- verify rendering succeeds;
- verify no WebGL context loss.

### 9. Source policy

Source checks are guardrails, not a sandbox. Flag or reject direct use of:

- `ctx.space` or engine internals;
- direct `pymunk` imports;
- `js`, OS, subprocess, filesystem, network, `eval`, or `exec` APIs;
- unsupported imports.

An initial import allowlist may include:

```text
math
dataclasses
enum
ebm.tile_api
ebm.ports
```

## CI result and merge policy

The validator should emit both human-readable and machine-readable reports, for example:

```text
Metadata             PASS
Source policy        PASS
Build bounds         PASS
Resource ownership   PASS
Contract tests       PASS
Neighbor tests       PASS
Cleanup              PASS
Performance          PASS
Browser smoke        PASS
```

A future near-automatic merge policy can require:

- all mandatory checks green;
- no new external dependencies;
- changes limited to permitted contribution paths;
- generated tile snapshot or preview present;
- minimal maintainer review for relevance and obvious inappropriate content.

## Repository organization

No immediate decision is required.

Start in the main repository, for example:

```text
tiles/
  builtin/
  contributed/
```

This simplifies early API changes and CI. Once the API stabilizes and contribution volume warrants it, `contributed/` can move to a separate repository without changing the runtime model.

## Port and routing decision

The current leading port model is a uniform signature on every tile:

```text
Inputs:  T0, L0, R0
Outputs: B0, L1, R1
```

All six bijective input/output permutations are valid contribution contracts. Map policy and contract validity are deliberately separate.

The built-in fallback generator should prefer the three permutations without same-side horizontal returns (`L0 -> L1` or `R0 -> R1`), because repeated same-side defaults create frequent two-tile loops. Authored contributed tiles remain free to use any of the six permutations.

Routing choice is also separate from concrete tile implementation choice. A coordinate first selects a required permutation; the engine then selects a compatible authored implementation, falling back to a quiet built-in tile only when necessary.

This model is implemented in `ebm/routes.py` with `ALL_ROUTES`, `DEFAULT_ROUTES`, `RouteSelection`, and `route_at()`. All six permutations have collision-driven reference implementations and pass strict sampled validation (`243/243` each). The three no-same-side-return routes remain the default map policy.

The capability foundation is implemented in `ebm/tile_api.py`: `TileBuilder`, opaque handles, bounds checks, engine-owned resources, ownership validation, automatic cleanup, visual-only primitives, and centralized ball-contact dispatch. The old `Contract`, `TileContext`, and `FillerTile` systems have been removed.

The reference routers are intentionally temporary and visually quiet. They use tile-owned Pymunk sensors and callbacks, never scan `space.bodies`, and receive no direct `Space` access. Their bounded steering should eventually be replaced by authored physical mechanisms.

## Proposed implementation sequence

1. Define `TileBuilder` and opaque handle types.
2. Add an engine-owned resource registry around the shared Pymunk space.
3. Remove direct `TileContext.space` exposure from the public tile API.
4. Enforce local-coordinate and bounds validation.
5. Add automatic resource-arena cleanup.
6. Implement central ball-contact dispatch.
7. Migrate one simple static filler to the new API.
8. Migrate one powered filler using conveyors, motors, constraints, or contact events.
9. Add ownership, cleanup, and bounds tests.
10. Remove the global `space.bodies` polling helpers from built-in fillers.
11. Rerun and strengthen the port-contract validator.
12. Add neighbor, isolation, scaling, and browser validation incrementally.

## Guiding principle

> Tiles are reviewed Python components that program a local physical mechanism through an owned API. They do not program the global physics world.
