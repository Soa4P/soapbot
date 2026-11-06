"""Read-only watchdog for resident plugin workers.

Deliberately does NOT restart anything
-------------------------------------
The supervisor already owns crash recovery, with backoff and a circuit that only an
operator can reset. A watchdog that also killed or restarted processes would hide a
hostile plugin behind a green light and could fight the circuit breaker. This script
only *observes* and reports, so the same explicit-recovery rule holds everywhere.

It checks, without writing any business data:

* the container is running and healthy via ``docker compose ps``;
* the number of ``-I -c`` worker children, against the configured ceiling;
* ``Z``-state children of the container (a zombie is a reaping bug, not a crash);
* the loopback health endpoint.

``--self-test`` exercises the parsing/reporting logic with synthetic input and never
touches docker, the network or the filesystem. Exit codes: 0 healthy, 1 warning,
2 could not inspect.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

COMPOSE = Path(os.environ.get("SOAPBOT_COMPOSE_FILE", "/opt/soapbot/deploy/docker-compose.yml"))
HEALTH_URL = os.environ.get("SOAPBOT_GUARD_HEALTH_URL", "http://127.0.0.1:6185/api/health")
DEFAULT_MAX_WORKERS = 16
COMMAND_TIMEOUT = 10

#: Matches the resident worker's argv: ``python -I -c <script>``. The one-shot runner
#: uses the same shape, so both are counted; that is intentional, they are both
#: plugin processes paid for by this host.
_WORKER_RE = re.compile(r"(?:^|\s)-I\s+-c\s")


@dataclass
class Report:
    checked_at: float
    container: str = ""
    container_status: str = ""
    worker_processes: int = 0
    max_workers: int = DEFAULT_MAX_WORKERS
    zombies: int = 0
    health: str = "unknown"
    warnings: list[str] = field(default_factory=list)
    restart_performed: bool = False


def configured_max() -> int:
    raw = os.environ.get("SOAPBOT_MAX_PLUGIN_WORKERS", str(DEFAULT_MAX_WORKERS))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_WORKERS
    return value if 1 <= value <= 64 else DEFAULT_MAX_WORKERS


def parse_ps(text: str) -> tuple[int, int]:
    """Return (worker processes, zombies) from ``ps -eo pid,ppid,stat,args``."""
    workers = 0
    zombies = 0
    for line in text.splitlines()[1:]:
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        stat, args = parts[2], parts[3]
        if _WORKER_RE.search(args):
            workers += 1
            if stat.startswith("Z"):
                zombies += 1
    return workers, zombies


def parse_compose(text: str) -> tuple[str, str]:
    """Return (name, status) from ``docker compose ps --format json`` output."""
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("Service") == "soapbot" or "soapbot" in str(row.get("Name", "")):
            return str(row.get("Name", "")), str(row.get("Status", ""))
    return "", ""


def probe_health(url: str = HEALTH_URL, timeout: float = 5.0) -> str:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read(512).decode("utf-8", "replace")
            return "ok" if response.status == 200 and '"status":"ok"' in body.replace(" ", "") else "degraded"
    except (urllib.error.URLError, OSError, ValueError):
        return "unreachable"


def _run(argv: list[str]) -> str:
    completed = subprocess.run(
        argv, capture_output=True, text=True, timeout=COMMAND_TIMEOUT, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError(f"{argv[0]} exited {completed.returncode}")
    return completed.stdout


def inspect() -> Report:
    report = Report(checked_at=time.time(), max_workers=configured_max())
    try:
        name, status = parse_compose(
            _run(["docker", "compose", "-f", str(COMPOSE), "ps", "--format", "json"])
        )
        report.container, report.container_status = name, status
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        report.warnings.append(f"container inspect failed: {type(exc).__name__}")
    try:
        workers, zombies = parse_ps(
            "pid ppid stat args\n" + _run(["ps", "-eo", "pid,ppid,stat,args"])
        )
        report.worker_processes, report.zombies = workers, zombies
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        report.warnings.append(f"process inspect failed: {type(exc).__name__}")
    report.health = probe_health()

    if not report.container:
        report.warnings.append("soapbot container is not running")
    elif "healthy" not in report.container_status.lower():
        report.warnings.append("soapbot container is not reporting healthy")
    if report.worker_processes > report.max_workers:
        report.warnings.append(
            f"worker processes {report.worker_processes} exceed cap {report.max_workers}"
        )
    if report.zombies:
        report.warnings.append(f"{report.zombies} zombie plugin process(es) not reaped")
    if report.health != "ok":
        report.warnings.append(f"health endpoint is {report.health}")
    return report


def self_test() -> Report:
    """Deterministic report used by offline tests; no docker, network or files."""
    ps = (
        "pid ppid stat args\n"
        "100 1 Ss python -I -c plugin-worker-script\n"
        "101 100 Z python -I -c one-shot-runner-script\n"
        "102 1 Ss /usr/bin/dockerd\n"
    )
    workers, zombies = parse_ps(ps)
    name, status = parse_compose('{"Name":"deploy-soapbot-1","Service":"soapbot","Status":"Up (healthy)"}')
    report = Report(
        checked_at=0.0,
        container=name,
        container_status=status,
        worker_processes=workers,
        zombies=zombies,
        health="ok",
        max_workers=2,
    )
    if workers > report.max_workers:
        report.warnings.append("synthetic over-capacity detected")
    if zombies:
        report.warnings.append("synthetic zombie detected")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only plugin worker watchdog")
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument("--self-test", action="store_true", help="offline parsing check")
    args = parser.parse_args(argv)

    report = self_test() if args.self_test else inspect()
    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
    else:
        print(
            f"container={report.container or '(none)'} status={report.container_status or '(none)'}\n"
            f"workers={report.worker_processes}/{report.max_workers} zombies={report.zombies} "
            f"health={report.health} restart_performed={report.restart_performed}"
        )
        for warning in report.warnings:
            print(f"WARN {warning}")
    if args.self_test:
        parsed = (
            report.worker_processes == 2
            and report.zombies == 1
            and report.container_status == "Up (healthy)"
        )
        return 0 if parsed else 2
    if any("inspect failed" in w for w in report.warnings):
        return 2
    return 1 if report.warnings else 0


if __name__ == "__main__":
    sys.exit(main())
