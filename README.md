# Endless Ball Machine

A browser-based, community-built ball machine running real-time Python/pymunk physics.

This repo is currently in prototype/scaffolding.

- Planning doc: [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md)

## Prototype 0

Prototype 0 is a filler-only endless browser simulation. It proves the Pyodide + pymunk + Canvas2D loop before adding contributed tile loading.

Run locally with uv:

```bash
uv sync --extra dev
uv run python -m ebm serve --port 8000
```

Then open:

```text
http://127.0.0.1:8000/web/
```

Controls:

- Drag/pan the canvas
- Arrow keys pan
- Click/tap to drop a ball

Run tests:

```bash
uv run pytest
```

## Static site build

Build the deployable static site:

```bash
./scripts/build-static-site.sh
```

The default output is:

```text
dist/site/
```

Deploy to the current viblo.se folder mapping:

```bash
./scripts/build-static-site.sh
rm -rf /var/www/endless-ball-machine
mkdir -p /var/www/endless-ball-machine
cp -a dist/site/. /var/www/endless-ball-machine/
```

Expected URL:

```text
https://endless-ball-machine.viblo.se/
```

## Debug simulator

Open a single filler/tile contract with port overlays and automatic entry-port ball spawning:

```text
https://endless-ball-machine.viblo.se/debug.html
```

Local URL while serving:

```text
http://127.0.0.1:8000/web/debug.html
```

## Validation

Validate all current filler contracts from the command line:

```bash
uv run python -m ebm validate
```

Machine-readable output for CI/pipelines:

```bash
uv run python -m ebm validate --json
```

The command exits non-zero if any filler contract fails. The debug page also shows a short validation result for the selected contract.
