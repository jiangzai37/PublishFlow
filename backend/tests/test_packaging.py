import importlib.util
from pathlib import Path

PACKAGE_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "package.py"
SPEC = importlib.util.spec_from_file_location("publishflow_package", PACKAGE_SCRIPT)
assert SPEC and SPEC.loader
package_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package_module)


def test_portable_package_excludes_sensitive_files(tmp_path, monkeypatch):
    excluded_files = (
        "backend/.env",
        "backend/.env.local",
        "backend/publishflow.db",
        "backend/publishflow.db-wal",
        "backend/publishflow.sqlite3",
        "backend/pytest-of-user/pytest-0/test_case/main.py",
        "frontend/.credential.key",
        "scripts/credentials.json",
    )
    safe_files = ("backend/app/main.py", "frontend/src/main.ts", ".env.example")
    for relative in (*excluded_files, *safe_files):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test", encoding="utf-8")

    monkeypatch.setattr(package_module, "ROOT", tmp_path)
    included = {path.relative_to(tmp_path).as_posix() for path in package_module.portable_files()}

    assert set(safe_files) <= included
    assert included.isdisjoint(excluded_files)
