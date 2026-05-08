"""Low-RAM execution guard for Phase 10 reliable runtime.

The guard is intentionally small and dependency-free. It can run before stories,
targeted tests, migrations, gateway restarts, model probes, and reviewer calls.
It never mutates system state; it only returns an allow/block decision.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BLOCKED_BY_COST_OPERATIONS = {
    "agent_loop",
    "model_probe",
    "reviewer_call",
    "story",
}


@dataclass(frozen=True)
class ResourceThresholds:
    min_available_ram_mb: int = 300
    max_disk_used_percent: float = 85.0
    max_load_per_cpu: float = 1.5
    require_gateway_active: bool = True


@dataclass(frozen=True)
class ResourceSnapshot:
    available_ram_mb: int
    total_ram_mb: int
    swap_used_mb: int
    swap_total_mb: int
    disk_used_percent: float
    load_1m: float
    cpu_count: int
    gateway_status: str = "unknown"
    top_memory_processes: list[dict[str, Any]] = field(default_factory=list)
    daily_cost_total_usd: float | None = None
    daily_cost_limit_usd: float | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class ResourceDecision:
    allowed: bool
    operation: str
    blocked_reasons: list[str]
    warnings: list[str]
    snapshot: ResourceSnapshot

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "operation": self.operation,
            "blocked_reasons": self.blocked_reasons,
            "warnings": self.warnings,
            "snapshot": asdict(self.snapshot),
        }


def _read_meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    for raw in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if ":" not in raw:
            continue
        key, rest = raw.split(":", 1)
        parts = rest.strip().split()
        if not parts:
            continue
        try:
            values[key] = int(parts[0]) // 1024
        except ValueError:
            continue
    return values


def _service_status(service: str) -> str:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return (result.stdout or result.stderr or "unknown").strip() or "unknown"
    except Exception:
        return "unknown"


def _top_memory_processes(limit: int = 5) -> list[dict[str, Any]]:
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid,user,pmem,rss,comm", "--sort=-rss"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return []
    rows = []
    for raw in result.stdout.splitlines()[1 : limit + 1]:
        parts = raw.split(None, 4)
        if len(parts) != 5:
            continue
        pid, user, pmem, rss, command = parts
        try:
            rows.append(
                {
                    "pid": int(pid),
                    "user": user,
                    "mem_percent": float(pmem),
                    "rss_mb": int(rss) // 1024,
                    "command": command,
                }
            )
        except ValueError:
            continue
    return rows


def _read_env_value(name: str, default: str | None = None) -> str | None:
    for env_path in ("/srv/automation/.env", str(Path.home() / ".hermes" / ".env")):
        try:
            for raw in Path(env_path).read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if line.startswith(f"{name}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            continue
    return os.environ.get(name, default)


def _daily_cost_state() -> tuple[float | None, float | None]:
    limit_raw = _read_env_value("HERMES_DAILY_COST_LIMIT_USD", "2.00")
    try:
        limit = float(limit_raw or "2.00")
    except ValueError:
        limit = 2.0
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = Path.home() / ".hermes" / "cost-guardrail" / f"{day}.jsonl"
    if not path.exists():
        return 0.0, limit
    total = 0.0
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            total += float(json.loads(raw).get("amount_usd") or 0.0)
        except Exception:
            continue
    return total, limit


def collect_snapshot(*, disk_path: str = "/", top_n: int = 5) -> ResourceSnapshot:
    mem = _read_meminfo()
    disk = shutil.disk_usage(disk_path)
    disk_used_percent = ((disk.total - disk.free) / disk.total) * 100 if disk.total else 100.0
    load_1m = os.getloadavg()[0]
    cpu_count = os.cpu_count() or 1
    cost_total, cost_limit = _daily_cost_state()
    return ResourceSnapshot(
        available_ram_mb=mem.get("MemAvailable", 0),
        total_ram_mb=mem.get("MemTotal", 0),
        swap_used_mb=max(0, mem.get("SwapTotal", 0) - mem.get("SwapFree", 0)),
        swap_total_mb=mem.get("SwapTotal", 0),
        disk_used_percent=round(disk_used_percent, 2),
        load_1m=round(load_1m, 2),
        cpu_count=cpu_count,
        gateway_status=_service_status("hermes-gateway"),
        top_memory_processes=_top_memory_processes(top_n),
        daily_cost_total_usd=cost_total,
        daily_cost_limit_usd=cost_limit,
    )


def assess_resources(
    snapshot: ResourceSnapshot,
    *,
    operation: str,
    thresholds: ResourceThresholds | None = None,
) -> ResourceDecision:
    thresholds = thresholds or ResourceThresholds()
    blocked: list[str] = []
    warnings: list[str] = []

    if snapshot.available_ram_mb < thresholds.min_available_ram_mb:
        blocked.append(
            f"available_ram_mb {snapshot.available_ram_mb} < {thresholds.min_available_ram_mb}"
        )

    if snapshot.disk_used_percent > thresholds.max_disk_used_percent:
        blocked.append(
            f"disk_used_percent {snapshot.disk_used_percent:.1f} > {thresholds.max_disk_used_percent:.1f}"
        )

    max_load = max(1, snapshot.cpu_count) * thresholds.max_load_per_cpu
    if snapshot.load_1m > max_load:
        blocked.append(f"load_1m {snapshot.load_1m:.2f} > {max_load:.2f}")

    if thresholds.require_gateway_active and operation != "diagnostics":
        if snapshot.gateway_status != "active":
            blocked.append(f"hermes-gateway status is {snapshot.gateway_status}")

    if operation in BLOCKED_BY_COST_OPERATIONS:
        total = snapshot.daily_cost_total_usd
        limit = snapshot.daily_cost_limit_usd
        if total is not None and limit is not None and limit > 0 and total > limit:
            blocked.append(f"daily_cost_total_usd {total:.4f} > {limit:.4f}")

    if snapshot.swap_total_mb and snapshot.swap_used_mb > snapshot.swap_total_mb * 0.4:
        warnings.append(
            f"swap_used_mb {snapshot.swap_used_mb} is high for swap_total_mb {snapshot.swap_total_mb}"
        )

    return ResourceDecision(
        allowed=not blocked,
        operation=operation,
        blocked_reasons=blocked,
        warnings=warnings,
        snapshot=snapshot,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hermes Phase 10.R Resource Guard")
    parser.add_argument("--operation", default="story")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    decision = assess_resources(collect_snapshot(), operation=args.operation)
    if args.json:
        print(json.dumps(decision.to_dict(), indent=2, ensure_ascii=False))
    else:
        status = "allow" if decision.allowed else "block"
        print(f"resource_guard={status}")
        for reason in decision.blocked_reasons:
            print(f"blocked_reason={reason}")
        for warning in decision.warnings:
            print(f"warning={warning}")
    return 0 if decision.allowed else 75


if __name__ == "__main__":
    raise SystemExit(main())
