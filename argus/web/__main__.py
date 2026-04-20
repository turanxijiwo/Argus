"""CLI entry: python -m argus.web"""
import argparse

import uvicorn

from .app import app


def main() -> None:
    p = argparse.ArgumentParser(description="Argus Web Dashboard")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5173)
    p.add_argument("--reload", action="store_true")
    args = p.parse_args()
    uvicorn.run(
        "argus.web.app:app" if args.reload else app,
        host=args.host, port=args.port, reload=args.reload,
    )


if __name__ == "__main__":
    main()
