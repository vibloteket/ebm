# Flow Tile API v1

Tiles do not route identified balls. Every tile accepts the fixed inputs `T0`, `L0`, and `R0`; a ball may leave through any valid output (`B0`, `L1`, or `R1`).

A tile class has metadata plus `build(builder)` and optional `update(builder, dt)`. It has no route constructor argument and no `routes` property.

Ball contacts use Pymunk's `begin`, `pre_solve`, `post_solve`, and `separate` phases through safe `ContactEvent` values. Registering callbacks does not change a shape's physical behavior: static segments and circles collide, while sensor boxes remain non-colliding. `begin` and `pre_solve` may return `False` to disable collision processing.

Strict validation runs one concurrent stream of 120 balls, balanced across all inputs with varied entry states. There is no drain phase. At every step, at most 20 balls may remain active inside the tile, whether buffered or in transit. At completion, every entered ball must be either a valid exit or still physically present inside; loss, invalid exits, non-finite state, and removal are failures. All three outputs must be exercised.
