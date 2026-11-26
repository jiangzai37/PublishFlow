#!/usr/bin/env python3
import os
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def wait_for_url(
    url: str, processes: list[subprocess.Popen], timeout: float = 45
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for process in processes:
            if process.poll() is not None:
                raise RuntimeError(f"服务进程提前退出，退出码 {process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError(f"服务启动超时：{url}")


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        process.terminate()
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    load_env()
    api_host = os.environ.get("APP_HOST", "127.0.0.1")
    api_port = int(os.environ.get("APP_PORT", "8765"))
    web_host = os.environ.get("FRONTEND_HOST", "127.0.0.1")
    web_port = int(os.environ.get("FRONTEND_PORT", "5173"))
    connect_host = "127.0.0.1" if api_host in {"0.0.0.0", "::"} else api_host
    browser_host = "127.0.0.1" if web_host in {"0.0.0.0", "::"} else web_host
    python = (
        ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    npm = "npm.cmd" if os.name == "nt" else "npm"
    if not python.exists():
        print(
            "未找到项目虚拟环境，请先运行 start.bat 或 scripts/start.sh。",
            file=sys.stderr,
        )
        return 1

    processes: list[subprocess.Popen] = []
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    try:
        api_process = subprocess.Popen(
            [
                str(python),
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                api_host,
                "--port",
                str(api_port),
            ],
            cwd=ROOT / "backend",
            env=env,
            start_new_session=os.name != "nt",
        )
        processes.append(api_process)
        web_process = subprocess.Popen(
            [npm, "--prefix", "frontend", "run", "dev"],
            cwd=ROOT,
            env=env,
            start_new_session=os.name != "nt",
        )
        processes.append(web_process)
        wait_for_url(f"http://{connect_host}:{api_port}/api/health", processes)
        wait_for_url(f"http://{browser_host}:{web_port}", processes)
        print(f"PublishFlow 已启动：http://{browser_host}:{web_port}")
        webbrowser.open(f"http://{browser_host}:{web_port}")
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        raise RuntimeError("某个服务进程已退出，请检查上方日志")
    except KeyboardInterrupt:
        print("\n正在停止 PublishFlow…")
    except (OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        for process in reversed(processes):
            stop_process(process)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
