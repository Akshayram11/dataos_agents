#!/usr/bin/env python3
"""Run the Botsky dashboard and always-on gateway in one DataOS container."""

from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import time


STOPPING = False


def command(*parts: str) -> list[str]:
    return ["/opt/hermes/.venv/bin/hermes", *parts]


def main() -> int:
    global STOPPING

    home = Path(os.environ.get("HERMES_HOME", "/opt/data"))
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    gateway_log = (log_dir / "dataos-gateway-supervisor.log").open("ab", buffering=0)

    dashboard = subprocess.Popen(
        command(
            "dashboard",
            "--host",
            os.environ.get("HERMES_DASHBOARD_HOST", "0.0.0.0"),
            "--port",
            os.environ.get("HERMES_DASHBOARD_PORT", "9119"),
            "--no-open",
        )
    )
    gateway: subprocess.Popen[bytes] | None = None

    def stop(_signum: int, _frame: object) -> None:
        global STOPPING
        STOPPING = True
        for process in (dashboard, gateway):
            if process is not None and process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    delay = 1.0
    try:
        while not STOPPING:
            if dashboard.poll() is not None:
                STOPPING = True
                break

            if gateway is None or gateway.poll() is not None:
                if gateway is not None:
                    print(
                        f"[dataos] gateway exited with code {gateway.returncode}; restarting in {delay:.0f}s",
                        file=sys.stderr,
                        flush=True,
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, 30.0)
                gateway = subprocess.Popen(
                    command("gateway", "run", "--replace"),
                    stdout=gateway_log,
                    stderr=subprocess.STDOUT,
                )
                print(f"[dataos] gateway started pid={gateway.pid}", flush=True)

            time.sleep(1.0)
    finally:
        for process in (gateway, dashboard):
            if process is not None and process.poll() is None:
                process.terminate()
        for process in (gateway, dashboard):
            if process is not None:
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        gateway_log.close()

    return dashboard.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
