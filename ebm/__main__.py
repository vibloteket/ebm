from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import sys
import webbrowser


def serve(port: int, open_browser: bool) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), SimpleHTTPRequestHandler)
    url = f"http://127.0.0.1:{port}/web/"
    print(f"Serving Endless Ball Machine at {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server")


def validate(json_output: bool, duration: float, balls_per_entry: int) -> int:
    from .validator import results_to_json, validate_all_fillers_port_spec

    results = validate_all_fillers_port_spec(duration=duration)
    if json_output:
        print(results_to_json(results))
    else:
        for result in results:
            print(result.summary())
        total = len(results)
        passed = sum(1 for result in results if result.ok)
        print(f"\n{passed}/{total} filler contracts passed")
    return 0 if all(result.ok for result in results) else 1


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m ebm")
    sub = parser.add_subparsers(dest="command")

    serve_parser = sub.add_parser("serve", help="serve the browser prototype")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--open", action="store_true", help="open the browser")

    validate_parser = sub.add_parser("validate", help="validate filler tile contracts")
    validate_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    validate_parser.add_argument("--duration", type=float, default=12.0)
    validate_parser.add_argument("--balls-per-entry", type=int, default=6)

    args = parser.parse_args(argv)
    if args.command in (None, "serve"):
        serve(getattr(args, "port", 8000), getattr(args, "open", False))
    elif args.command == "validate":
        raise SystemExit(validate(args.json, args.duration, args.balls_per_entry))
    else:
        parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
