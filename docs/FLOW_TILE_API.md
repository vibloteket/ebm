# Flow Tile API v2

Tiles do not route identified balls. Every tile accepts the fixed inputs `T0`, `L0`, and `R0`; a ball may leave through any valid output (`B0`, `L1`, or `R1`).

A tile class has metadata plus `build(builder)` and optional `update(builder, dt)`. It has no route constructor argument and no `routes` property.

Strict validation runs one concurrent stream of 120 balls, balanced across all inputs with varied entry states. There is no drain phase. At every step, at most 20 balls may remain active inside the tile, whether buffered or in transit. At completion, every entered ball must be either a valid exit or still physically present inside; loss, invalid exits, non-finite state, and removal are failures. All three outputs must be exercised.
