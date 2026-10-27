# Flow Tile API v1

Tiles do not route identified balls. Every tile accepts the fixed inputs `T0` and `L0`; a ball may leave through either valid output, `B0` or `R0`.

A tile class has metadata plus `build(builder)` and optional `update(builder, dt)`. It has no route constructor argument and no `routes` property.

Ball contacts use Pymunk's `begin`, `pre_solve`, `post_solve`, and `separate` phases through safe `ContactEvent` values. Registering callbacks does not change a shape's physical behavior: static segments and circles collide, while sensor boxes remain non-colliding. `begin` and `pre_solve` may return `False` to disable collision processing.

Strict validation runs one concurrent stream of 120 balls, balanced across both inputs with varied entry states. There is no drain phase. At every step, at most 20 balls may remain active inside the tile, whether buffered or in transit. At completion, every entered ball must be either a valid exit or still physically present inside; loss, invalid exits, non-finite state, and removal are failures. Both outputs must be exercised.

## Visual-only circles

`ctx.visual_circle(center, radius, *, fill_color=DEFAULT_CIRCLE_FILL,
stroke_color=DEFAULT_CIRCLE_STROKE, foreground=False)` draws a circle without
adding a collision shape or body. The center is tile-local, and the entire
circle must fit within the tile. Radius must be finite and nonnegative.

```python
# Decorative ring; foreground=True draws it after balls.
ring = ctx.visual_circle((200, 200), 40, fill_color=None,
                         stroke_color=(40, 80, 160, 255), foreground=True)
ring.set_stroke_color((80, 120, 200, 255))
# ctx.remove(ring) removes it from rendering.
```

Returns an owned `VisualHandle`, like `visual_segment`, `visual_polygon`, and
`visual_box`. `None` disables fill or stroke independently. Circles render in
the live scene, editor preview, and debug view; they do not affect ball routing.

## World layout

The world uses staggered columns. Even columns have no vertical offset; odd columns are shifted down by 200 units. `R0 = (400, 300)` therefore meets the next column's `L0 = (0, 100)`. Every handoff goes either down (`B0 → T0`) or right (`R0 → L0`), so a ball can never return to an earlier tile and map-level flow loops are structurally impossible.
