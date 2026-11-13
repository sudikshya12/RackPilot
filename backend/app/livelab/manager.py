"""Live-lab manager. Every observation here is REAL (source LOCAL_LAB), collected on this machine
from a process the lab itself owns. It never inspects or changes other host services.

Safety:
* The target is started with a fixed argv list (no shell, no interpolation of user input).
* Stop and kill apply only to the PID the lab started, and only after the /health marker matches.
* Disabled by default; the operator enables it in Settings.
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx

from ..config import BASE_DIR, get_settings
from ..models import utcnow
from .target import MARKER

LOG_PATH = BASE_DIR / "data" / "livelab-target.log"
PID_PATH = BASE_DIR / "data" / "livelab-target.pid"

COLLECTORS_META = [
    {"key": "http_check", "label": "HTTP health check (real)", "group": "service", "recommended": True},
    {"key": "process_info", "label": "Process information for lab target (real)", "group": "process", "recommended": True},
    {"key": "listening_sockets", "label": "TCP listener check (real)", "group": "network", "recommended": True},
    {"key": "journalctl", "label": "Lab target log tail (real)", "group": "logs", "recommended": True},
]
REPAIRS_META = [
    {"key": "start_target", "label": "Start the lab target service",
     "description": "Real action: launches the lab-owned target process on 127.0.0.1.", "tests_hypothesis": "svc_stopped",
     "requires_spare_workflow": False},
]

_proc: Optional[subprocess.Popen] = None


def _port() -> int:
    return get_settings().livelab_port


def _read_pid() -> Optional[int]:
    try:
        return int(PID_PATH.read_text().strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid: Optional[int]) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def health() -> dict[str, Any]:
    url = f"http://127.0.0.1:{_port()}/health"
    t0 = time.perf_counter()
    try:
        r = httpx.get(url, timeout=1.5)
        ms = round((time.perf_counter() - t0) * 1000, 1)
        ok = r.status_code == 200 and r.json().get("service") == MARKER
        return {"ok": ok, "status_code": r.status_code, "latency_ms": ms, "body": r.text[:300], "url": url,
                "pid": r.json().get("pid") if ok else None}
    except httpx.HTTPError as e:
        return {"ok": False, "status_code": None, "latency_ms": None, "error": f"{type(e).__name__}: {e}", "url": url}


def status() -> dict[str, Any]:
    pid = _read_pid()
    h = health()
    return {"pid": pid, "pid_alive": _pid_alive(pid), "health": h, "port": _port(), "bind": "127.0.0.1"}


def start_target() -> dict[str, Any]:
    global _proc
    if health()["ok"]:
        return status()
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "-m", "app.livelab.target", "--port", str(int(_port())), "--log", str(LOG_PATH)]
    _proc = subprocess.Popen(argv, cwd=str(BASE_DIR), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    PID_PATH.write_text(str(_proc.pid))
    for _ in range(30):
        if health()["ok"]:
            break
        time.sleep(0.1)
    return status()


def stop_target() -> dict[str, Any]:
    """Stop ONLY the lab-owned target, and only if PID and marker agree."""
    pid = _read_pid()
    h = health()
    if not h["ok"]:
        return status()
    if pid is None or h.get("pid") != pid:
        raise RuntimeError("Refusing to stop: the process on the lab port is not the PID this lab started.")
    os.kill(pid, signal.SIGTERM)
    for _ in range(30):
        if not _pid_alive(pid):
            break
        time.sleep(0.1)
    return status()


def collect(collector: str) -> dict[str, Any]:
    port = _port()
    if collector == "http_check":
        h = health()
        out = (f"GET {h['url']}\nHTTP {h['status_code']}  ({h['latency_ms']} ms)\n{h.get('body', '')}" if h["status_code"]
               else f"GET {h['url']}\n{h.get('error')}")
        return {"command": f"httpx GET {h['url']} (timeout 1.5 s)", "output": out, "observations": {"http_ok": h["ok"]},
                "interpretation": "Health endpoint answered with the lab marker." if h["ok"] else
                "No healthy response. A refused connection means nothing is listening on the port.",
                "limitations": "Real observation on this machine, limited to the lab-owned target."}
    if collector == "process_info":
        pid = _read_pid()
        alive = _pid_alive(pid)
        return {"command": f"os.kill({pid}, 0)  # liveness probe of lab-started PID", "output":
                f"pid file: {PID_PATH.name}\nrecorded pid: {pid}\nprocess alive: {alive}",
                "observations": {"pid": pid, "alive": alive},
                "interpretation": "Lab target process is running." if alive else "The lab-started process is not running.",
                "limitations": "Checks only the PID this lab started; other host processes are not inspected."}
    if collector == "listening_sockets":
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        try:
            rc = s.connect_ex(("127.0.0.1", port))
        finally:
            s.close()
        listening = rc == 0
        return {"command": f"connect(127.0.0.1:{port})", "output": f"connect_ex returned {rc} ({'LISTEN' if listening else os.strerror(rc)})",
                "observations": {"listening": listening},
                "interpretation": f"Something is listening on 127.0.0.1:{port}." if listening else f"No listener on 127.0.0.1:{port}.",
                "limitations": "TCP connect test only; does not enumerate other sockets."}
    if collector == "journalctl":
        try:
            lines = LOG_PATH.read_text(errors="replace").splitlines()[-15:]
        except OSError:
            lines = ["(no log file yet)"]
        return {"command": f"tail -n 15 {LOG_PATH.name}", "output": "\n".join(_sanitize(l) for l in lines),
                "observations": {"lines": len(lines)}, "interpretation": "Verbatim tail of the lab target's own log.",
                "limitations": "Only the lab target's log is read. Lines are sanitized for tokens and passwords."}
    raise KeyError(collector)


def _sanitize(line: str) -> str:
    import re
    return re.sub(r"(?i)(token|password|secret|authorization)[=:]\s*\S+", r"\1=[redacted]", line)[:500]


def apply_repair(action_key: str) -> str:
    if action_key != "start_target":
        raise KeyError(action_key)
    start_target()
    return "Real action: started the lab-owned target process on 127.0.0.1."


_healthy_since_repair = {"n": 0}


def note_probe(ok: bool, repaired: bool) -> None:
    _healthy_since_repair["n"] = _healthy_since_repair["n"] + 1 if (ok and repaired) else 0


def verify() -> list[dict]:
    h = health()
    st = status()
    n = _healthy_since_repair["n"]
    return [
        {"key": "http_health", "name": "GET /health returns 200 with lab marker", "passed": h["ok"],
         "observed": f"HTTP {h['status_code']}" if h["status_code"] else h.get("error", "no response"), "expected": "HTTP 200"},
        {"key": "process_alive", "name": "Lab-started process is alive", "passed": st["pid_alive"],
         "observed": str(st["pid_alive"]), "expected": "True"},
        {"key": "post_repair_samples", "name": "2 consecutive healthy probes after the repair", "passed": n >= 2,
         "observed": f"{n} healthy probe(s)", "expected": ">= 2"},
    ]
