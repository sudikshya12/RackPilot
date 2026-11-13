#!/usr/bin/env python3
"""RackOps Lab: read-only Linux hardware collector.

Run it on the machine under test, then upload the JSON on the intake page:

    python3 rackops_collect.py --data-iface eth1 > observations.json

Safety and scope
----------------
* Read-only. It reads /proc and /sys and runs `lsblk -J`, `ip -j`, and (only if present and
  permitted) `smartctl -H -j` / `dmesg`. It never writes to disk, changes settings, or loads modules.
* Commands use fixed argv lists. No shell is invoked and no user input is interpolated.
* Anything that is unavailable or not permitted is reported as {"_unsupported": "<reason>"},
  never as zero, so the acceptance engine routes it to MANUAL REVIEW.
* Standard library only (Python 3.8+).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _run(argv: list[str], timeout: float = 8.0):
    if shutil.which(argv[0]) is None:
        return None, f"{argv[0]} not installed"
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"{argv[0]} failed: {e}"
    if p.returncode != 0 and not p.stdout:
        return None, (p.stderr.strip() or f"{argv[0]} exited {p.returncode}")[:200]
    return p.stdout, None


def _read(path: str):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def identity():
    serial = _read("/sys/class/dmi/id/product_serial")  # usually root-only
    out = {"serial_number": serial, "manufacturer": _read("/sys/class/dmi/id/sys_vendor"),
           "model": _read("/sys/class/dmi/id/product_name"), "bios_version": _read("/sys/class/dmi/id/bios_version")}
    if not any(out.values()):
        return {"_unsupported": "DMI information not readable (/sys/class/dmi/id)"}
    if serial is None:
        out["note"] = "product_serial requires root; serial not reported"
    return out


def cpu():
    txt = _read("/proc/cpuinfo")
    if not txt:
        return {"_unsupported": "/proc/cpuinfo not readable"}
    models = re.findall(r"^model name\s*:\s*(.+)$", txt, re.M)
    sockets = set(re.findall(r"^physical id\s*:\s*(\d+)$", txt, re.M))
    return {"count": len(sockets) or (1 if models else None), "model": models[0] if models else None, "cores_total": len(models) or None}


def memory():
    txt = _read("/proc/meminfo")
    m = re.search(r"^MemTotal:\s+(\d+) kB", txt or "", re.M)
    if not m:
        return {"_unsupported": "/proc/meminfo not readable"}
    # Kernel-visible total, below installed capacity; the check applies a documented tolerance.
    return {"total_gib": round(int(m.group(1)) / 1024 / 1024, 2), "basis": "meminfo", "dimms": []}


def storage():
    out, err = _run(["lsblk", "-J", "-d", "-b", "-o", "NAME,SIZE,ROTA,TRAN,MODEL,TYPE"])
    if out is None:
        return {"_unsupported": err}
    disks = []
    for d in json.loads(out).get("blockdevices", []):
        if d.get("type") != "disk" or d["name"].startswith(("loop", "ram", "zram")):
            continue
        tran = (d.get("tran") or "").lower()
        kind = "nvme" if d["name"].startswith("nvme") or tran == "nvme" else ("hdd" if str(d.get("rota")) in ("1", "True", "true") else "ssd")
        disks.append({"name": d["name"], "size_gb": round(int(d["size"]) / 1e9), "type": kind, "model": (d.get("model") or "").strip()})
    return disks


def disk_health(disks):
    if os.geteuid() != 0:
        return {"_unsupported": "SMART/NVMe health needs root; re-run with sudo to collect it"}
    if shutil.which("smartctl") is None:
        return {"_unsupported": "smartctl not installed"}
    if not isinstance(disks, list):
        return {"_unsupported": "no disk inventory"}
    res = []
    for d in disks:
        out, err = _run(["smartctl", "-H", "-j", f"/dev/{d['name']}"])
        if out is None:
            res.append({"name": d["name"], "smart_passed": None, "error": err})
            continue
        j = json.loads(out)
        res.append({"name": d["name"], "smart_passed": (j.get("smart_status") or {}).get("passed"),
                    "media_errors": (j.get("nvme_smart_health_information_log") or {}).get("media_errors")})
    return res


def nics(data_iface: str | None):
    base = Path("/sys/class/net")
    if not base.exists():
        return {"_unsupported": "/sys/class/net not present"}
    out = []
    for p in sorted(base.iterdir()):
        if not (p / "device").exists():  # skip virtual interfaces (lo, bridges, veth)
            continue
        speed = _read(str(p / "speed"))
        try:
            speed_v = int(speed) if speed is not None and int(speed) > 0 else None
        except ValueError:
            speed_v = None
        carrier = _read(str(p / "carrier"))
        out.append({"name": p.name, "mac": _read(str(p / "address")), "speed_mbps": speed_v,
                    "link": carrier == "1" if carrier is not None else None,
                    "role": "data" if p.name == data_iface else "unknown"})
    return out


def connectivity(target: str | None):
    if not target:
        out, _ = _run(["ip", "-j", "route", "show", "default"])
        try:
            target = json.loads(out)[0]["gateway"] if out else None
        except (ValueError, IndexError, KeyError):
            target = None
    if not target:
        return {"_unsupported": "No default gateway found and no --gateway given"}
    out, err = _run(["ping", "-c", "3", "-W", "1", target], timeout=10)
    rtt = re.search(r"= [\d.]+/([\d.]+)/", out or "")
    return {"target": target, "gateway_reachable": out is not None and " 0% packet loss" in out,
            "rtt_ms": float(rtt.group(1)) if rtt else None, **({"error": err} if err else {})}


def kernel_errors():
    out, err = _run(["dmesg", "--level=err,warn"])
    if out is None:
        return {"_unsupported": f"dmesg not readable ({err}); kernel.dmesg_restrict may require root"}
    pat = re.compile(r"(mce|machine check|EDAC|AER|I/O error|nvme.*(timeout|reset)|link is not ready|hardware error)", re.I)
    return {"lines": [l[:300] for l in out.splitlines() if pat.search(l)][-50:]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data-iface", help="name of the data-network interface (tags it role=data)")
    ap.add_argument("--gateway", help="address to ping for the connectivity check")
    a = ap.parse_args()
    if platform.system() != "Linux":
        print(json.dumps({"_meta": {"collector": "linux_collector", "error": f"Unsupported platform: {platform.system()}"}}))
        return
    disks = storage()
    obs = {
        "identity": identity(), "cpu": cpu(), "memory": memory(), "storage": disks, "disk_health": disk_health(disks),
        "nics": nics(a.data_iface), "connectivity": connectivity(a.gateway), "kernel_errors": kernel_errors(),
        "redfish": {"_unsupported": "Host collector does not query the BMC"},
        "_meta": {"collector": "linux_collector/1.0", "collected_at": datetime.now(timezone.utc).isoformat(),
                  "host": socket.gethostname(), "euid": os.geteuid(), "kernel": platform.release()},
    }
    print(json.dumps(obs, indent=2))


if __name__ == "__main__":
    main()
