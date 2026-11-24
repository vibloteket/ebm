# Endless Ball Machine

A browser-based, community-built ball machine running real-time Python/pymunk physics.

The complete machine runs in the visitor's browser using Pyodide and Pymunk. Hosting is static; no application server or authoring-agent environment is required.

## Main-machine physics selection

The main machine defaults to **Pymunk 7.4.0 with the baseline solver**.
The [admin page](https://ebm.viblo.se/admin.html) links to comparison views:

- `/?pymunk=7.3.1#stats`: previous Pymunk release (baseline only).
- `/?solver=auto#stats`: 7.4.0 with automatic acceleration (Wasm SIMD when available).
- `/#stats`: current default with the performance popup.

On 7.4.0, the popup's Auto solver checkbox switches live, without resetting the
machine. It updates the URL and starts a fresh profiling window. Reports include
the loaded Pymunk version and selected solver. `auto` is a selection policy,
not a guarantee of acceleration; it falls back to baseline if unavailable.
Accelerated solvers can change simulation results slightly and may not be faster.

Version changes require a reload. Settings are URL-only, not persisted in local
storage. Unknown versions/modes produce a startup error; `solver=auto` on 7.3.1
uses baseline and disables the checkbox. The editor, demos, and other tools
remain pinned to 7.3.1 and ignore these parameters.

## Add or disable a tile

1. Build and manually validate your tile in the browser editor, then download its `.py` file.
2. In GitHub, open [`ebm/tiles/contributed/`](ebm/tiles/contributed/) and use **Add file → Upload files**. Use a Python filename such as `my_scanner.py`.
3. Define exactly one `TileBase` subclass and set `author`. `enabled` defaults to `True`.
4. Commit to `main`. The **Validate and publish machine** workflow discovers the file, checks every enabled tile, builds the entire site, and publishes only after success.

No catalog, JavaScript file list, or machine-selection list needs editing. Subdirectories are supported. Public `.py` files under `ebm/tiles/` are tiles; files/directories starting with `_` are helpers or package initializers.

To keep an unfinished tile without blocking publication:

```python
class MyScanner(TileBase):
    author = "Your name"
    enabled = False
```

Disabled tiles remain downloadable and editable, labelled **[disabled]** in the editor. Publication skips their construction and flow tests; the machine excludes them. Explicit manual Run/Validate in the editor still works. Syntax, imports, and metadata must remain valid, including a real boolean for `enabled`. At least one tile must be enabled to publish. The two builtin routing examples are disabled by default.

The machine selects uniformly from the sorted enabled catalog using `WORLD_SEED` and tile coordinates. Panning, reloads and different visitors agree for the same catalog. Adding, disabling or renaming a tile may rearrange existing positions. Filenames form tile identity, so avoid needless renames.

## Tile API and animation

See [the Flow Tile API](docs/FLOW_TILE_API.md) for visual primitives and
[animation helpers](docs/ANIMATION.md) for `Tween`, setter callbacks, completion
handling, and the standard `ease` functions. The browser editor's API help also
includes signatures and a growing-circle recipe.

## Local development

Run locally with uv:

```bash
uv sync --extra dev
uv run python -m ebm serve --port 8000
```

Then open:

```text
http://127.0.0.1:8000/
```

Controls:

- Drag/pan the canvas
- Arrow keys pan
- Click/tap to drop a ball

Run tests:

```bash
uv run --extra dev python -m pytest
```

## Static site build

Build the deployable static site:

```bash
uv run bash scripts/build-static-site.sh
```

The default output is:

```text
dist/site/
```

## Quick editor feedback

- Live simulation marks balls red when they fail the validator's full-passage exit checks (wrong edge, aperture or angle). Exit markers show the reason for eight simulation seconds, even after the ball disappears. Run or changing preview mode clears them. The 3 × 3 preview checks each tile handoff too.
- **Stop on first failure** defaults to on and remembers your choice in this browser. Validation retains the first detected failure and its replay, marks incomplete runs **Stopped early**, and skips the repeat test if single-tile flow fails. Uncheck it for the full report. Output balance is only judged at the end; a temporary imbalance does not stop a run.
- Validation controls (Validate flow, fail-fast and Seed) appear only in **Validation** mode. The optional **Seed** accepts a decimal integer from `0` to `4294967295`; blank generates a fresh seed. Results show the actual seed and fill the textbox for reruns; clear it for another random seed.
- CI generates a fresh seed per publication run, prints `Validation seed: …` in its log, and records top-level `seed` in the `tile-validation` artifact's `validation.json`, even on validation failure. Reproduce with `python -m ebm validate --seed 123 --json`, or enter that seed in the browser using the same tile source. Disable fail-fast for a full report matching CI.
- Each tile's single and repeat stages reset Python's global `random` to that seed, including tile construction/build/update/callback calls. Repeat input generation uses the same seed. The prior global random state is restored afterward, so preview activity and catalog order do not shift validation randomness.
- Independent unseeded `random.Random()` instances, `secrets`, wall-clock values and randomness during source import/compilation are not controlled. Browser/native physics can still differ numerically; a matching seed does not promise identical trajectories across runtimes.
- Preview feedback is advisory, not a replacement for full validation. Publication checks still run the full validators.

## GitHub Pages publication

The workflow in [`.github/workflows/pages.yml`](.github/workflows/pages.yml) runs on commits to `main` and can be rerun manually. Pull requests run the checks without deployment.

- Installs locked Python dependencies, checks syntax and runs unit tests.
- Runs full single-tile and homogeneous 3 × 3 validation for **each enabled tile** with a recorded, randomly generated run seed. No random mixed-grid gate or exhaustive combination tests.
- Saves `validation.json` as the `tile-validation` Actions artifact for diagnostics.
- Builds the site, tile manifest and Python package file list.
- Deploys only after all checks succeed. Failed builds leave the previous deployment in place; publication runs are serialized.

The build job has read-only repository access and no deployment secrets. The separate deploy job has Pages/OIDC permissions. There is no SSH, `/var/www` access or dependency on the original development environment.

**One-time setup:** in GitHub **Settings → Pages**, set **Source → GitHub Actions**. If deployment ran before this was enabled, rerun the workflow. Initial URL:

```text
https://vibloteket.github.io/ebm/
```

**Custom domain, when ready:** configure `endless-ball-machine.viblo.se` in Pages settings, then change that subdomain's DNS to a CNAME pointing to `vibloteket.github.io` (no path). Complete any GitHub domain-verification request and enable HTTPS when its certificate is ready. Until then, the existing custom-domain site can remain unchanged; this workflow neither modifies DNS nor deploys to the old host.

The local `serve` command builds the same artifact before serving it, so generated catalogs and nested tile modules also work locally.

## Debug simulator

Open a single filler/tile contract with port overlays and automatic entry-port ball spawning:

```text
https://endless-ball-machine.viblo.se/debug.html
```

Local URL while serving:

```text
http://127.0.0.1:8000/debug.html
```

## Validation

Run the same enabled-tile publication checks locally:

```bash
uv run python -m ebm validate
```

Machine-readable output for CI/pipelines:

```bash
uv run python -m ebm validate --json
```

The command exits non-zero if an enabled tile fails, metadata/imports are invalid, or there are no enabled tiles. Disabled tiles are reported as skipped. The debug page remains a reference simulator; the editor can test any selected tile explicitly.

### Picking positions in the tile editor

The preview shows live **tile-local (x, y)** coordinates beneath the canvas,
using one decimal place. Move the pointer over a tile to see its position;
clicks still spawn balls. There are no pin or copy controls.

In the 3 × 3 preview, coordinates remain local to the tile under the pointer
(including staggered columns), not world or screen pixels. Margins and gaps
show no coordinates. The readout works while paused too.

### Ball supply

The nominal source rate is **0.8 balls per second across a tile's two inputs**:

- Single-tile validation and automatic debug spawning alternate T0/L0 every 1.25 seconds.
- Editor preview uses independent 1.875–3.125 second intervals per open input (2.5 seconds on average).
- Repeated validation and the main machine use 2.5 seconds per open boundary input.

The shared timing constants live in `ebm/ball_physics.py`. These control sources, not transfers between tiles: upstream mechanisms may still produce bursts or concentrate flow. Initial machine inventory and manual ball spawning are unchanged.

## License

Endless Ball Machine is free software licensed under the
[GNU Affero General Public License v3.0 or later](LICENSE).
