#!/usr/bin/env python3
"""
One-click Docker builder/runner for Cosbrain.

Features:
- Check Docker/Compose availability and start Docker Desktop on Windows if needed
- Prepare .env (copy from .env.example if missing) and create bind-mount directories
- Build app image and compose up db/redis/minio/app
- Wait for services and perform a basic health check on the API

Usage:
    python docker/oneclick_docker.py           # build and start all
    python docker/oneclick_docker.py --no-build # skip build, just up
    python docker/oneclick_docker.py --logs     # follow app logs after start
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str] | str, check: bool = True, capture: bool = False, shell: bool = False):
    print(f"$ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    if capture:
        return subprocess.run(cmd, check=check, capture_output=True, text=True, shell=shell)
    return subprocess.run(cmd, check=check, shell=shell)


def ensure_docker_running(timeout: int = 120):
    try:
        run(["docker", "--version"], check=True)
        run(["docker", "compose", "version"], check=True)
    except subprocess.CalledProcessError:
        raise SystemExit("Docker or Docker Compose not found. Please install Docker Desktop.")

    # Check daemon
    try:
        r = run(["docker", "info", "--format", "{{.ServerVersion}}"], check=True, capture=True)
        if r.returncode == 0 and r.stdout.strip():
            print(f"Docker Engine: {r.stdout.strip()}")
            return
    except subprocess.CalledProcessError:
        pass

    # Try to start Docker Desktop on Windows
    if platform.system() == "Windows":
        dd = Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Docker" / "Docker" / "Docker Desktop.exe"
        if dd.exists():
            print("Starting Docker Desktop...")
            subprocess.Popen([str(dd)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            print("Docker Desktop executable not found; waiting for engine if starting manually...")

    # Wait
    print("Waiting for Docker Engine to be ready...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = run(["docker", "info", "--format", "{{.ServerVersion}}"], check=True, capture=True)
            if r.returncode == 0 and r.stdout.strip():
                print(f"Docker Engine: {r.stdout.strip()}")
                return
        except subprocess.CalledProcessError:
            pass
        time.sleep(2)
    raise SystemExit("Docker Engine failed to start within timeout.")


def prepare_env_and_dirs():
    # .env
    env_file = ROOT / ".env"
    env_example = ROOT / ".env.example"
    if not env_file.exists() and env_example.exists():
        shutil.copyfile(env_example, env_file)
        print("Created .env from .env.example")

    # Bind-mount directories
    for p in [ROOT / "logs", ROOT / "uploaded_files", ROOT / "yara" / "output"]:
        p.mkdir(parents=True, exist_ok=True)
        # Ensure writable
        try:
            test_file = p / ".writable"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink(missing_ok=True)
        except Exception as e:
            print(f"Warning: directory not writable: {p} ({e})")


def docker_compose_up(no_build: bool = False):
    # Optional: pull base services for faster build
    try:
        run(["docker", "compose", "pull", "db", "redis", "minio", "minio-setup"], check=False)
    except Exception:
        pass

    if not no_build:
        run(["docker", "compose", "build", "app"], check=True)

    run(["docker", "compose", "up", "-d"], check=True)


def wait_for_app_health(timeout: int = 180) -> bool:
    # Try health endpoint
    import requests
    base = "http://localhost:8001"
    health_urls = [f"{base}/health", f"{base}/docs", f"{base}/openapi.json"]
    start = time.time()
    while time.time() - start < timeout:
        for url in health_urls:
            try:
                r = requests.get(url, timeout=3)
                if r.status_code in (200, 401, 403):
                    print(f"App healthy via {url} -> {r.status_code}")
                    return True
            except Exception:
                pass
        time.sleep(2)
    return False


def follow_app_logs():
    try:
        run(["docker", "compose", "logs", "-f", "app"], check=True)
    except KeyboardInterrupt:
        pass


def main():
    parser = argparse.ArgumentParser(description="Cosbrain one-click Docker builder/runner")
    parser.add_argument("--no-build", action="store_true", help="Skip image build; just compose up")
    parser.add_argument("--logs", action="store_true", help="Follow app logs after start")
    args = parser.parse_args()

    ensure_docker_running()
    prepare_env_and_dirs()
    docker_compose_up(no_build=args.no_build)

    ok = False
    try:
        ok = wait_for_app_health()
    except Exception as e:
        print(f"Health check error: {e}")

    if ok:
        print("SUCCESS: App is up at http://localhost:8001 (docs at /docs)")
    else:
        print("WARNING: App health not confirmed; check logs below")
        run(["docker", "compose", "ps"], check=False)

    if args.logs:
        follow_app_logs()


if __name__ == "__main__":
    # Ensure working directory is project root when launched directly
    os.chdir(ROOT)
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e}")
        sys.exit(e.returncode)
    except SystemExit as e:
        raise
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)
