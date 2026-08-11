# Flow Tile API v1

Tiles do not route identified balls. Every tile accepts the fixed inputs `T0` and `L0`; a ball may leave through either valid output, `B0` or `R0`.

A tile class has metadata plus `build(builder)` and optional `update(builder, dt)`. It has no route constructor argument and no `routes` property.

Ball contacts use Pymunk's `begin`, `pre_solve`, `post_solve`, and `separate` phases through safe `ContactEvent` values. Registering callbacks does not change a shape's physical behavior: static segments and circles collide, while sensor boxes remain non-colliding. `begin` and `pre_solve` may return `False` to disable collision processing.

Strict validation runs one concurrent stream of 120 balls, balanced across both inputs with varied entry states. There is no drain phase. At every step, at most 20 balls may remain active inside the tile, whether buffered or in transit. At completion, every entered ball must be either a valid exit or still physically present inside; loss, invalid exits, non-finite state, and removal are failures. Both outputs must be exercised.

The world uses staggered columns. Even columns have no vertical offset; odd columns are shifted down by 200 units. `R0 = (400, 300)` therefore meets the next column's `L0 = (0, 100)`. Every handoff goes either down (`B0 → T0`) or right (`R0 → L0`), so a ball can never return to an earlier tile and map-level flow loops are structurally impossible.
