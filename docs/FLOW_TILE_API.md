# Flow Tile API v2

Tiles do not route identified balls. Every tile accepts the fixed inputs `T0`, `L0`, and `R0`; a ball may leave through any valid output (`B0`, `L1`, or `R1`).

A tile class has metadata plus `build(builder)` and optional `update(builder, dt)`. It has no route constructor argument and no `routes` property.

Strict validation samples 243 input position/velocity states, requires every ball to leave through a valid output with a valid handoff state, rejects loss/stalls/out-of-bounds balls, and requires all three outputs to be exercised across the test.
