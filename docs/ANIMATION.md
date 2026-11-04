# Tween animation helpers

Import the helpers from the public tile API:

```python
from ebm import Tween, ease
```

A `Tween` interpolates **one finite scalar value** from start to end over a
specified number of simulation seconds. It does not run itself, read a wall
clock, alter physics automatically, or register with a global animation manager.
The tile owns it and calls `update(dt)` from its existing update method.

## Growing a circle

```python
# In build(self, builder), or when starting an effect:
self.circle = builder.visual_circle((200, 200), 1, dynamic=True)
self.growth = Tween(
    1, 15, duration=2.0,
    apply=self.circle.set_radius,
    easing=ease.in_out_sine,
)

# In update(self, builder, dt):
if self.growth is not None:
    self.growth.update(dt)
    if self.growth.done:
        self.growth = None
        # The circle is now exactly radius 15.
```

Use the real ball's `ball.radius` instead of 15 when making a stand-in for a
paused ball. Pause and teleport the real ball using its normal handle methods.
When the tween finishes, remove the visual stand-in and resume the real ball.
The stand-in is not a collision shape. Keep track of each ball/effect separately
if multiple effects may run concurrently.

`dynamic=True` avoids rebuilding the static tile bitmap for each radius change.
The setter still checks that the circle fits inside the tile.

## Contract

```python
Tween(start, end, *, duration, apply=None, easing=ease.linear)
```

- `start` and `end`: finite scalar numbers, in either direction; equal values are allowed.
- `duration`: finite, nonnegative seconds. Zero completes on the first update,
  including `update(0)`; construction itself does not apply anything.
- `apply`: optional callable accepting one float. Pass a bound setter directly,
  such as `circle.set_radius`, or a lambda for custom work.
- `easing`: callable mapping normalized time `[0, 1]` to interpolation progress.
  Defaults to linear. Custom functions are supported.
- `value`: read-only current value, initially `start`.
- `done`: read-only completion flag, initially `False`.
- `update(dt)`: advances by finite, nonnegative simulation seconds, applies the
  new value if a callback exists, and returns it. Large steps stop at the end;
  completion applies the **exact** `end`, then sets `done=True`.
- Further updates on a completed tween return the final value without applying
  it again. Invalid `dt` is still rejected.
- `update(0)` on an unfinished, positive-duration tween applies its current value
  without advancing time. Easing is bypassed at the exact endpoints.

Without `apply`, use the returned value or read `value`:

```python
self.growth = Tween(1, 15, duration=2)
# update:
self.circle.set_radius(self.growth.update(dt))
```

Each call advances time, so call `update(dt)` only once per simulation update.
Using the supplied `dt` keeps the effect independent of rendering frame rate.
A simulation pause pauses the effect because updates stop.

## Easing functions

Use `ease.linear`, or `ease.in_<family>`, `ease.out_<family>`, and
`ease.in_out_<family>` for each of these standard families:

| Family | Behaviour |
| --- | --- |
| `sine` | Gentle sinusoidal acceleration/deceleration |
| `quad`, `cubic`, `quart`, `quint` | Increasingly pronounced polynomial easing |
| `expo` | Strong exponential acceleration/deceleration |
| `circ` | Circular-arc easing |
| `back` | Anticipation/overshoot |
| `elastic` | Oscillating spring-like overshoot |
| `bounce` | Bouncing approach to an endpoint |

For example: `ease.in_quad`, `ease.out_bounce`, `ease.in_out_sine`.
These are progress curves, not physical simulations. Direct calls to easing
functions expect time in `[0, 1]`.

**Back and elastic can produce progress below 0 or above 1.** Interpolated values
are deliberately not clamped. This can make a radius negative or move geometry
outside tile bounds, causing the normal setter to reject it. Prefer bounded
curves such as sine/polynomial easing for radius changes near limits. The exact
start and end values are preserved even with custom easing.

## Ownership, errors, and scope

A tween holding a bound method also holds a reference to its target. Stop
updating and drop the tween **before removing its target**; there is no automatic
cancellation or target-lifetime detection. Dropping the reference cancels future
updates—there is no background task to stop.

Callback and easing exceptions propagate. A failed update does not advance the
tween's internal time/value/done state; external side effects already performed
by a callback cannot be undone. Non-finite easing/interpolated values are rejected
before calling `apply`. Bounds and ownership errors are not silently swallowed.

There are deliberately no completion callbacks, loops, timelines, automatic
property binding, or vector/color interpolation in this first version. Completion
logic stays explicit in the tile's update method; no special cleanup is needed
when a tile and its tweens are discarded together.
