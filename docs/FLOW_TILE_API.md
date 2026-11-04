# Flow Tile API v1

Tiles do not route identified balls. Every tile accepts the fixed inputs `T0` and `L0`; a ball may leave through either valid output, `B0` or `R0`.

A tile class has metadata plus `build(builder)` and optional `update(builder, dt)`. It has no route constructor argument and no `routes` property.

Ball contacts use Pymunk's `begin`, `pre_solve`, `post_solve`, and `separate` phases through safe `ContactEvent` values. Registering callbacks does not change a shape's physical behavior: static segments and circles collide, while sensor boxes remain non-colliding. `begin` and `pre_solve` may return `False` to disable collision processing.

Strict validation runs one concurrent stream of 120 balls, balanced across both inputs with varied entry states. There is no drain phase. At every step, at most 20 balls may remain active inside the tile, whether buffered or in transit. At completion, every entered ball must be either a valid exit or still physically present inside; loss, invalid exits, non-finite state, and removal are failures. Both outputs must be exercised.

## Visual-only circles

`ctx.visual_circle(center, radius, *, fill_color=DEFAULT_CIRCLE_FILL,
stroke_color=DEFAULT_CIRCLE_STROKE, dynamic=False, foreground=False)` draws a circle without
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

## Animated visual primitives

All four visual builders—`visual_segment`, `visual_circle`, `visual_polygon`,
and `visual_box`—accept `dynamic=True`. This draws them outside the static
bitmap cache, so geometry or color updates do not rebuild that cache. The
coordinates remain tile-local; dynamic does not mean physical or automatically
moving. `foreground=True` works independently and draws after balls.
Defaults remain `dynamic=False`.

A circle's `VisualHandle.set_radius(radius)` changes its radius without replacing
the handle, center, colors, or rendering flags. It accepts finite, nonnegative
radii only, and the resized circle must still fit entirely within the tile.
Invalid changes leave the circle unchanged. Other visual types reject this
method; it does not resize physical balls or shapes.

```python
# build(): a stand-in for a paused ball at its destination
self.appearance = ctx.visual_circle((200, 200), 1, dynamic=True)

# update(): grow toward the real ball's normal radius
self.appearance.set_radius(animated_radius)
# When finished, remove the stand-in and resume the real ball.
```

For reusable timing and interpolation, use [`Tween` and `ease`](ANIMATION.md):

```python
from ebm import Tween, ease

# When starting the effect:
self.growth = Tween(1, ball.radius, duration=2,
                    apply=self.appearance.set_radius, easing=ease.in_out_sine)
# In update():
if self.growth is not None:
    self.growth.update(dt)
    if self.growth.done:
        self.growth = None
        # Remove the stand-in and resume the paused ball here.
```

Segments retain `set_segment_points(a, b)`.  Polygon/box geometry setters are
not added here; `dynamic=True` also makes their color animation inexpensive.

## World layout

The world uses staggered columns. Even columns have no vertical offset; odd columns are shifted down by 200 units. `R0 = (400, 300)` therefore meets the next column's `L0 = (0, 100)`. Every handoff goes either down (`B0 → T0`) or right (`R0 → L0`), so a ball can never return to an earlier tile and map-level flow loops are structurally impossible.
