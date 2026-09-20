"""Launch API, frontend and one detection worker; Ctrl+C stops all children."""
import argparse
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    node = shutil.which("node")
    if not node:
        raise SystemExit("Node.js not found. Install Node.js 22.12+ or 24 LTS.")
    for port in (8000, 5173):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise SystemExit(f"Port {port} is occupied. Stop the existing service first.")
    logs = ROOT / ".runtime"
    logs.mkdir(exist_ok=True)
    processes = []
    streams = []
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        for name, command, directory in [
            ("backend", [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000"], ROOT),
            ("frontend", [node, str(ROOT / "frontend/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", "5173", "--strictPort"], ROOT / "frontend")
        ]:
            stream = (logs / f"{name}.log").open("w", encoding="utf-8")
            streams.append(stream)
            processes.append(subprocess.Popen(command, cwd=directory, stdout=stream,
                                               stderr=subprocess.STDOUT, creationflags=flags))
        deadline = time.monotonic() + 45
        while True:
            if any(p.poll() is not None for p in processes):
                raise RuntimeError(f"A service exited. Read logs in {logs}")
            try:
                for url in ("http://127.0.0.1:8000/health", "http://127.0.0.1:5173"):
                    with urllib.request.urlopen(url, timeout=1) as response:
                        if response.status != 200:
                            raise OSError("Service not ready")
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"Startup timeout. Read logs in {logs}")
                time.sleep(.5)
        # API lifespan has created tables before the worker starts.
        worker_log = (logs / "worker.log").open("w", encoding="utf-8")
        streams.append(worker_log)
        processes.append(subprocess.Popen([sys.executable, "-m", "worker.worker"], cwd=ROOT,
            stdout=worker_log, stderr=subprocess.STDOUT, creationflags=flags))
        print("Ready: http://127.0.0.1:5173 | API: http://127.0.0.1:8000/docs", flush=True)
        print("Press Ctrl+C to stop all services.", flush=True)
        if not args.no_browser:
            webbrowser.open("http://127.0.0.1:5173")
        while all(p.poll() is None for p in processes):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        for stream in streams:
            stream.close()


if __name__ == "__main__":
    main()
