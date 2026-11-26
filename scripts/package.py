#!/usr/bin/env python3
import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    ".git",
    ".env",
    "credentials.json",
}


def is_sensitive_path(path: Path) -> bool:
    return (
        any(part.startswith((".env.", "tmp")) for part in path.parts)
        or path.name.startswith((".env.", "tmp"))
        or path.suffix in {".db", ".sqlite", ".sqlite3", ".key", ".pem"}
        or any(
            path.name.endswith(suffix)
            for suffix in (".db-wal", ".db-shm", ".db-journal")
        )
    )


def run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def portable_files() -> list[Path]:
    files: list[Path] = []
    for directory in ("backend", "frontend", "scripts", ".github"):
        base = ROOT / directory
        if not base.exists():
            continue
        for path in base.rglob("*"):
            relative_parts = path.relative_to(ROOT).parts
            if (
                not path.is_file()
                or EXCLUDED_PARTS.intersection(relative_parts)
                or any(part.startswith("pytest-of-") for part in relative_parts)
            ):
                continue
            if path.suffix in {".pyc", ".tsbuildinfo", ".log"} or is_sensitive_path(
                path.relative_to(ROOT)
            ):
                continue
            if (
                directory == "frontend"
                and "dist" not in relative_parts
                and "src" not in relative_parts
                and path.name
                not in {
                    "package.json",
                    "package-lock.json",
                    "index.html",
                    "vite.config.ts",
                    "tsconfig.json",
                    "tsconfig.app.json",
                    "tsconfig.node.json",
                }
            ):
                continue
            files.append(path)
    files.extend(
        ROOT / name
        for name in (
            ".env.example",
            ".gitignore",
            ".dockerignore",
            ".impeccable.md",
            "Dockerfile",
            "docker-compose.yml",
            "LICENSE",
            "README.md",
            "start.bat",
        )
        if (ROOT / name).exists()
    )
    return sorted(set(files))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a portable PublishFlow source package"
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Use the existing frontend production build",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "release")
    args = parser.parse_args()
    npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if not npm:
        print("未找到 npm，无法构建便携包。", file=sys.stderr)
        return 1
    if not args.skip_build:
        run([npm, "ci"], ROOT / "frontend")
        run([npm, "run", "build"], ROOT / "frontend")
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        print("前端构建不存在，请先构建或去掉 --skip-build。", file=sys.stderr)
        return 1

    version = json.loads(
        (ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    )["version"]
    args.output.mkdir(parents=True, exist_ok=True)
    destination = args.output / f"publishflow-{version}-portable.zip"
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in portable_files():
            archive.write(path, Path("PublishFlow") / path.relative_to(ROOT))
    print(f"便携包已生成：{destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
