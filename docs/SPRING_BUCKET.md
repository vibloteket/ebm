# Spring Bucket

`ebm/tiles/contributed/spring_bucket.py` is a passive spring-suspended collector with an actively controlled hatch. `MIN_BALLS = 5` is the initial threshold, for the standard radius-15 balls.

- Both inputs feed the same bucket. The bucket is a real dynamic compound body, free to swing and rotate.
- A damped spring carries its weight; a slack rope constraint limits maximum extension. Neither creates collision geometry. The cord and handle are visual-only dynamic segments.
- A massless polygon sensor follows the body. The controller counts ball centres inside the hopper, not all contacts in the sensor's bounding rectangle.
- When at least five balls are present, the hatch opens. It closes when one complete ball has cleared the bottom, normally leaving four behind. More arrivals can queue another opening after the short settling interval.
- The small raised finger is part of the hatch and opens/closes with it. It prevents symmetric seating that otherwise produces persistent two-ball arches above the narrow outlet. Simply removing a flat hatch passed short tests but eventually jammed.
- The hopper's sloping bottom, splitter and two outlet guides are passive physical geometry. The right-hand slope supplies speed; the downward throat removes excess sideways velocity. Output choice is physical, not an alternating controller.
- Only the hatch and its raised finger are paused/resumed. No ball/body position or velocity setters, transport surfaces, force/impulse calls, teleportation or artificial bucket stabilisation are used.

## API additions

`TileBuilder.spring()` and `rope()` join an owned body to a tile-local fixed anchor with a body-local attachment. They return ordinary ownership-checked constraint handles and participate in body pause/resume and owner cleanup. `sensor_polygon()` adds a massless body-local sensor.

`visual_segment(..., dynamic=True)` is for moving cords. Endpoint updates remain bounds-checked but do not rebuild the static tile bitmap on every frame. The main renderer draws these visuals in the dynamic layer. Old static-cache revisions are also correctly evicted by instance ID.

Geometry validation retains strict bounds. Immutable body-local shape geometry is cached; a conservative enclosing circle can prove an entire body is inside at any rotation. Bodies near an edge fall back to exact transformed shape bounds. Current pose and finite rotation are still checked, including after physics; adding a shape expands the bound. Tests compare transformed bounds against Pymunk with nonzero centre of gravity.

## Checks

- Single-tile flow at 120 Hz and 60 Hz, with one-ball-per-opening auditing.
- Four balls retained; adding the fifth releases exactly one.
- Homogeneous 3x3 flow; extended 90-second runs at both timestep settings and multiple seeds, checking retention and gate counts.
- Source audit permits active control only of the hatch assembly.
- Suspension load response, rope slack/limit, noncollision, sensor mass, ownership and cleanup.
- Pyodide/browser validation and preview; main-machine rendering with the full enabled catalog.

These are reproducible sampled tests, not a proof for arbitrary ball sizes, changed thresholds or unlimited inflow. Revalidate after changing geometry or parameters.
