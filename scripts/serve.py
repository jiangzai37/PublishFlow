#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Serve the PublishFlow production build"
    )
    parser.add_argument("--host", default=os.environ.get("APP_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("APP_PORT", "8765"))
    )
    args = parser.parse_args()
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        print(
            "缺少前端生产构建，请先运行 npm --prefix frontend run build。",
            file=sys.stderr,
        )
        return 1

    import uvicorn

    uvicorn.run(
        "app.main:app", host=args.host, port=args.port, app_dir=str(ROOT / "backend")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
