# Web Tile Editor Plan

Status: design proposal, implementation deferred

## Goal

Create an in-browser tile development environment for Endless Ball Machine. A contributor should be able to inspect existing tile source, modify a local working copy, run it immediately in Pyodide/Pymunk, preview it in isolation or repeated in a small world, validate its route contract, and export a Python file suitable for a pull request.

The editor should require no local installation and no server-side save system for the MVP.

## Proposed page

Add a dedicated static page:

```text
/editor.html
```

Desktop layout:

```text
+------------------------------+-------------------------------+
| Preview                      | Code editor                   |
|                              |                               |
| [Single] [3x3] [Validate]    | class MyTile(TileBase):      |
|                              |     ...                       |
| animated simulation          |                               |
|                              |                               |
+------------------------------+                               |
| status / validation result   | [Run] [Reset] [Download]     |
+------------------------------+-------------------------------+
```

On narrow screens, use tabs or stacked panes:

```text
[Preview] [Code] [Validation]
```

All user-facing UI text must be English, regardless of the language used in project discussions.

## Preview modes

### Single tile

Reuse the current tile-debug concept:

- one tile;
- visible port specification zones;
- balls emitted from all three inputs;
- selected `RoutePermutation`;
- click/tap to emit additional balls;
- Basic renderer by default;
- compact validation status.

### Repeated 3x3

Place nine instances of the edited tile in one shared Pymunk space:

```text
+---+---+---+
| A | A | A |
+---+---+---+
| A | A | A |
+---+---+---+
| A | A | A |
+---+---+---+
```

Use open-boundary spawning around the outside of the 3x3 region. This mode should expose problems that an isolated tile cannot show:

- port handoff failures;
- boundary overlap;
- repeating visual patterns;
- balls stuck between tiles;
- geometry extending beyond ownership bounds;
- mechanisms that interfere with neighbors;
- performance when a tile is repeated.

### Validation

Run the strict validator against every route declared by the tile. Present a clear table and detailed failures:

```text
Route                         Result
T0 -> B0, L0 -> R1, R0 -> L1 243/243 PASS

Unexpected exits              0
Out of bounds                 0
Stuck                         0
Active at timeout             0
```

For failures, include input port, sampled position/velocity, final position, final velocity, and failure category.

## Tile and source selection

The editor should allow selection among:

- New tile;
- built-in tiles;
- contributed tiles;
- locally stored drafts.

Selecting an existing tile loads its source as an editable working copy. The browser must never overwrite the original shipped source. Display a status such as:

```text
Editing a local copy of “Powered Channel”
```

Provide **Reset to original** for shipped tiles.

## Source organization

Implemented foundation: the runtime now uses one module per tile, explicit
`TILE_CLASS` exports, `ebm.tile_catalog`, and a build-generated tile manifest.
The editor UI itself remains deferred.

Use one module per tile:

```text
tiles/
  builtin/
    powered_channel.py
    reference_router.py
  contributed/
    contributor_name/
      water_wheel.py
```

A one-file-per-tile format simplifies:

- loading source into the editor;
- exporting a contribution;
- manifest generation;
- PR review;
- ownership and metadata checks;
- validation in CI.

Generate a tile manifest during the static build:

```json
{
  "tiles": [
    {
      "id": "ebm.powered-channel",
      "title": "Powered Channel",
      "author": "EBM",
      "module": "tiles/builtin/powered_channel.py",
      "class": "PoweredChannelTile",
      "routes": ["B0,R1,L1"]
    }
  ]
}
```

The editor uses this manifest to populate its source selector.

## Editor source format

Use an explicit exported class rather than guessing which class is the tile:

```python
from ebm import Port, RoutePermutation, TileBase

ROUTE = RoutePermutation({
    Port.T0: Port.B0,
    Port.L0: Port.R1,
    Port.R0: Port.L1,
})


class MyTile(TileBase):
    id = "local.my-tile"
    api_version = 1
    title = "My Tile"
    author = "Local editor"
    routes = (ROUTE,)

    def __init__(self, route):
        if route not in self.routes:
            raise ValueError(f"unsupported route: {route}")
        self.route = route

    def build(self, tile):
        tile.static_segment(
            (20, 80),
            (180, 120),
            radius=4,
            friction=0.8,
        )


TILE_CLASS = MyTile
```

`TILE_CLASS` is required for editor-loaded modules.

## Run lifecycle

When the user chooses **Run** or presses `Ctrl/Cmd + Enter`:

1. pause the preview;
2. retain the previous successful preview until the new build succeeds;
3. create a fresh Python namespace;
4. compile the editor source;
5. execute it;
6. resolve `TILE_CLASS`;
7. verify metadata and API version;
8. verify the selected route is supported;
9. destroy the previous successful tile instance and its resource arena;
10. create a fresh preview Pymunk space;
11. instantiate the tile through `TileBuilder`;
12. start the preview;
13. report build errors without losing the source draft.

Do not auto-run on every keystroke in the MVP. Continuous execution causes noisy syntax failures during ordinary typing and can repeatedly rebuild the physics world. A future optional “run after idle” mode may use a debounce around 700 ms.

## Error reporting

Show line-aware errors below the editor or in a dedicated panel:

```text
Build failed

Line 19
ValueError: point outside tile build bounds: (230, 80)
```

Distinguish at least:

- Python syntax error;
- execution/import error;
- missing `TILE_CLASS`;
- wrong `api_version`;
- invalid metadata;
- unsupported route;
- bounds violation;
- resource ownership violation;
- build exception;
- contact callback exception;
- validator failure;
- validator timeout.

Keep the last successful preview frozen or running until replacement code builds successfully.

## Persistence without a backend

A server-side save system is not required for the MVP. Use browser-local persistence.

### Local autosave

Store drafts in `localStorage`:

```text
ebm.editor.draft.<tile-id>
```

Store enough metadata to distinguish:

- source tile ID;
- local draft ID;
- modified timestamp;
- source text;
- selected route;
- selected preview mode.

The editor should restore an unsaved draft after reload and display **Modified locally**.

### Reset

For shipped tiles, **Reset to original** discards the local source override after confirmation.

### Import/export

Provide:

- **Download `.py`**;
- **Import `.py`**;
- optionally **Copy source**.

Use a sanitized filename based on tile ID, for example:

```text
vb-my-water-wheel.py
```

The downloaded file becomes the future PR contribution artifact.

### Possible later persistence

Future options, not part of MVP:

1. compressed shareable source URLs;
2. server-stored drafts;
3. GitHub OAuth;
4. “Open pull request” directly from the editor.

## Code editor component

### Preferred: CodeMirror 6

Use a vendored CodeMirror 6 bundle with:

- Python syntax highlighting;
- line numbers;
- bracket matching;
- automatic indentation;
- search;
- line/column display;
- diagnostics markers;
- mobile support.

Avoid loading editor dependencies from a third-party CDN in production.

### Minimal fallback

A styled `<textarea>` can serve as an initial implementation if CodeMirror bundling delays the workflow prototype. It must still support:

- tabs/indent insertion;
- `Ctrl/Cmd + Enter`;
- local autosave;
- error line reporting where possible.

Monaco is not recommended initially because of its larger weight and complexity.

## Pyodide runtime and hanging code

The simplest MVP executes preview code in the page’s existing Pyodide runtime. This is compatible with the project’s trust model: contributions are reviewed Python, and the browser tab is already an isolation boundary.

Known limitation:

```python
while True:
    pass
```

can hang the tab and require reload.

### Future worker architecture

A stronger editor can move validation into a disposable Web Worker:

```text
Main thread
- editor UI
- controls
- Canvas presentation

Worker
- Pyodide
- Pymunk
- contributed source
- strict validator
```

A validation timeout can terminate and recreate the worker. Interactive preview may remain in the main runtime initially, or later communicate scene state from a worker.

## Renderer behavior

Use **Basic** rendering by default in the editor and preview. It should reveal:

- actual collision shapes;
- visual-only shapes;
- sensors when debug display is enabled;
- dynamic bodies;
- joints and pivots;
- port zones;
- ball trajectories.

Allow switching to Pigment V3 for visual inspection, but do not make advanced rendering necessary for tile development.

A useful debug overlay should distinguish:

```text
physical shape  solid blue
visual-only     thin/dashed blue
sensor          translucent yellow
port input      green
port output     red
dynamic body    orange outline
joint           magenta marker
```

## TileBuilder API needed by the editor

The current API supports:

- `static_segment`;
- `static_circle`;
- `sensor_box`;
- `on_ball_contact`;
- `visual_segment`.

Before the editor can support mechanisms such as water wheels, add contributor-facing methods for:

- dynamic body creation;
- circle, segment, and polygon shapes attached to owned bodies;
- kinematic bodies;
- body position, angle, velocity, and angular-velocity accessors;
- pivot joints;
- simple motors;
- damped springs;
- rotary springs;
- gear joints;
- force and impulse application;
- bounded motor force and speed configuration;
- visual representation of dynamic bodies and joints.

All operations must remain tile-local, bounds-checked, ownership-checked, and automatically cleaned up through the tile’s resource arena.

## Validation integration

The editor should expose two validation levels.

### Quick validation

Fast feedback after a successful build:

- construction and cleanup;
- bounds;
- metadata;
- one nominal ball per input;
- short simulation;
- obvious stuck/out-of-bounds errors.

### Strict validation

Explicit **Validate** action:

- all `243` sampled entry states per route;
- exact mapped output, not merely any declared output;
- exit position and velocity specs;
- simultaneous balls;
- cleanup and ownership checks;
- repeated 3x3 behavior;
- resource counts;
- timing and callback counts.

Validation should run against every `RoutePermutation` in `TILE_CLASS.routes`.

## Existing tile source visibility

Built-in and contributed source should be readable in the editor. This is educational and gives contributors working examples.

The editor should show:

- title;
- author;
- tile ID;
- supported routes;
- original/read-only source indicator;
- local modification status;
- validation status from the shipped manifest if available.

Opening an existing tile always creates an editable local working copy; it does not mutate shipped files.

## MVP acceptance criteria

The first useful version is complete when a user can:

1. open `/editor.html`;
2. select a built-in tile or New tile;
3. inspect and edit Python source;
4. run with `Ctrl/Cmd + Enter`;
5. see a Basic-rendered Single preview;
6. switch to a repeated 3x3 preview;
7. choose a supported route;
8. receive syntax/build errors with line information;
9. run quick validation;
10. run strict validation;
11. reload the page without losing the draft;
12. reset a built-in tile to original source;
13. import and download a `.py` file;
14. navigate to the editor from `/admin.html`.

## Implementation sequence

1. **Done:** Move built-in tiles to one module per tile.
2. **Done:** Define tile source and metadata conventions, including required `TILE_CLASS`.
3. **Done:** Add the runtime tile catalog and generate a tile manifest during static-site build.
4. Extend `TileBuilder` with dynamic bodies, shapes, joints, and motors.
5. Add `/editor.html`, editor CSS, and startup diagnostics.
6. Add CodeMirror 6 or a temporary textarea editor.
7. Implement tile/source selection and editable local copies.
8. Add localStorage draft persistence.
9. Implement source compile/execute and fresh namespace loading.
10. Reuse/refactor debug preview for Single mode.
11. Add shared-space repeated 3x3 mode with boundary spawning.
12. Add Run, Reset, Import, and Download controls.
13. Add structured error display.
14. Add quick validation.
15. Integrate strict validation for all declared routes.
16. Add Basic/Pigment renderer switching and debug overlays.
17. Link the editor from `/admin.html`.
18. Later, move strict validation to a disposable Web Worker.

## Deferred decisions

The following do not block the MVP:

- main repository versus separate contributed-tile repository;
- GitHub authentication;
- automatic PR creation;
- server-side save;
- collaborative editing;
- hostile-code sandboxing;
- whether final EBM presentation permits zoom;
- production moderation and automatic merge thresholds.
