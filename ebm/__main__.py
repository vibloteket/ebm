from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from functools import partial
import json
import os
from pathlib import Path
import subprocess
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import sys
import webbrowser


def serve(port: int, open_browser: bool) -> None:
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")}
    subprocess.run(["bash", str(root / "scripts/build-static-site.sh")], check=True, env=env)
    handler = partial(SimpleHTTPRequestHandler, directory=str(root / "dist/site"))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Serving Endless Ball Machine at {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server")


def validate(json_output: bool) -> int:
    try:
        # Author print() calls are diagnostics, not part of the JSON report.
        with redirect_stdout(sys.stderr):
            from .publication import validate_publication
            report = validate_publication()
    except Exception as error:
        report = {"ok": False, "error": f"{type(error).__name__}: {error}", "tiles": []}
    if json_output:
        print(json.dumps(report, indent=2))
    else:
        for tile in report["tiles"]:
            print(f"{tile['id']}: {tile['status']}")
            if tile["status"] == "failed":
                print(json.dumps(tile, indent=2))
        if report.get("error"):
            print(report["error"])
        print("Publication checks: " + ("PASS" if report["ok"] else "FAIL"))
    return 0 if report["ok"] else 1


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m ebm")
    sub = parser.add_subparsers(dest="command")

    serve_parser = sub.add_parser("serve", help="serve the browser prototype")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--open", action="store_true", help="open the browser")

    validate_parser = sub.add_parser("validate", help="validate enabled tiles, single and homogeneous 3x3")
    validate_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")

    args = parser.parse_args(argv)
    if args.command in (None, "serve"):
        serve(getattr(args, "port", 8000), getattr(args, "open", False))
    elif args.command == "validate":
        raise SystemExit(validate(args.json))
    else:
        parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
