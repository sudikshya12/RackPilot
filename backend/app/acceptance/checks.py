"""Modular acceptance checks.

Every check is a small class with a stable ``key`` and a ``version``. It receives the expected
configuration and the observation set, and returns a ``CheckOutcome``. Checks never mutate input.

Result vocabulary: PASS | FAIL | MANUAL_REVIEW | UNSUPPORTED | SKIPPED | ERROR.
A missing observation section yields UNSUPPORTED ("Not collected"). It is never treated as zero
and never as a pass.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

RESULTS = ("PASS", "FAIL", "MANUAL_REVIEW", "UNSUPPORTED", "SKIPPED", "ERROR")


@dataclass
class CheckOutcome:
    result: str
    expected: Optional[str] = None
    observed: Optional[str] = None
    unit: Optional[str] = None
    detail: str = ""
    evidence_command: str = ""
    evidence_output: str = ""
    follow_up: list[str] = field(default_factory=list)


def _section(obs: dict, key: str):
    """Return (value, unsupported_reason)."""
    v = obs.get(key)
    if v is None:
        return None, "Not collected by this collector"
    if isinstance(v, dict) and "_unsupported" in v:
        return None, str(v["_unsupported"])
    return v, None


def _unsupported(reason: str, expected: Optional[str] = None, unit: Optional[str] = None) -> CheckOutcome:
    return CheckOutcome("UNSUPPORTED", expected=expected, observed="Not collected", unit=unit, detail=reason)


class Check:
    key = ""
    name = ""
    version = "1.0"
    description = ""

    def run(self, expected: dict, obs: dict) -> CheckOutcome:  # pragma: no cover - interface
        raise NotImplementedError


class HardwareIdentity(Check):
    key, name, version = "hardware_identity", "Hardware identity (serial number)", "1.1"
    description = "System serial number reported by firmware matches the intake record."

    def run(self, expected, obs):
        ident, why = _section(obs, "identity")
        if ident is None:
            return _unsupported(why, expected.get("serial_number"))
        serial = ident.get("serial_number")
        out = "\n".join(f"{k}: {v}" for k, v in ident.items())
        if not serial:
            return CheckOutcome("MANUAL_REVIEW", expected["serial_number"], "Not reported", detail="Firmware did not report a serial number; verify the chassis label manually.",
                                evidence_command="dmidecode -s system-serial-number", evidence_output=out)
        ok = serial.strip().upper() == expected["serial_number"].strip().upper()
        return CheckOutcome("PASS" if ok else "FAIL", expected["serial_number"], serial,
                            detail="" if ok else "Serial mismatch: the wrong chassis may have been delivered or labeled.",
                            evidence_command="dmidecode -t system", evidence_output=out,
                            follow_up=[] if ok else ["Confirm chassis label against the delivery manifest."])


class CpuInventory(Check):
    key, name = "cpu_inventory", "CPU inventory"
    description = "Socket count and model string match the expected configuration."

    def run(self, expected, obs):
        cpu, why = _section(obs, "cpu")
        exp = f"{expected['cpu_count']} × {expected['cpu_model']}"
        if cpu is None:
            return _unsupported(why, exp)
        count, model = cpu.get("count"), cpu.get("model") or ""
        observed = f"{count if count is not None else 'Unknown'} × {model or 'Unknown'}"
        out = f"Socket(s): {count}\nModel name: {model}\nCore(s) total: {cpu.get('cores_total', 'Unknown')}"
        if count is None or not model:
            return CheckOutcome("MANUAL_REVIEW", exp, observed, detail="CPU count or model not reported.", evidence_command="lscpu", evidence_output=out)
        ok = count == expected["cpu_count"] and expected["cpu_model"].lower() in model.lower()
        return CheckOutcome("PASS" if ok else "FAIL", exp, observed, None,
                            detail="" if ok else "CPU configuration differs from the order.", evidence_command="lscpu", evidence_output=out,
                            follow_up=[] if ok else ["Raise a configuration discrepancy with the vendor before handoff."])


class MemoryCapacity(Check):
    key, name, version = "memory_capacity", "Memory capacity", "1.2"
    description = ("Installed memory equals expected GiB. DIMM inventory is compared exactly. Kernel MemTotal is "
                   "accepted within 4 % because firmware and kernel reservations reduce the visible total.")

    def run(self, expected, obs):
        mem, why = _section(obs, "memory")
        exp_gib = float(expected["memory_gib"])
        if mem is None:
            return _unsupported(why, f"{exp_gib:g}", "GiB")
        total = mem.get("total_gib")
        basis = mem.get("basis", "dimm_inventory")
        dimms = mem.get("dimms") or []
        out_lines = [f"basis: {basis}", f"total: {total} GiB"] + [f"{d.get('slot')}: {d.get('size_gib')} GiB {d.get('type', '')}" for d in dimms]
        out = "\n".join(out_lines)
        if total is None:
            return CheckOutcome("MANUAL_REVIEW", f"{exp_gib:g}", "Unknown", "GiB", "Memory total not reported.", "dmidecode -t memory", out)
        if basis == "meminfo":
            ok = exp_gib * 0.96 <= total <= exp_gib * 1.0
            detail = "Compared kernel-visible MemTotal with 4 % tolerance (DIMM inventory unavailable without root)."
        else:
            ok = abs(total - exp_gib) < 0.01
            detail = ""
        if not ok:
            populated = len(dimms)
            detail = (f"Observed {total:g} GiB but {exp_gib:g} GiB expected"
                      + (f" ({populated} DIMMs populated)." if dimms else "."))
        return CheckOutcome("PASS" if ok else "FAIL", f"{exp_gib:g}", f"{total:g}", "GiB", detail,
                            "dmidecode -t memory" if basis != "meminfo" else "grep MemTotal /proc/meminfo", out,
                            [] if ok else ["Install missing DIMMs per the platform population guide, then re-test."])


class StorageInventory(Check):
    key, name = "storage_inventory", "Storage inventory"
    description = "Each expected drive is present with matching type and capacity (±2 %)."

    def run(self, expected, obs):
        disks, why = _section(obs, "storage")
        exp = expected.get("storage", [])
        exp_s = ", ".join(f"{d['count']}× {d['size_gb']} GB {d['type']}" for d in exp)
        if disks is None:
            return _unsupported(why, exp_s)
        out = "\n".join(f"{d.get('name')}  {d.get('size_gb')} GB  {d.get('type')}  {d.get('model', '')}" for d in disks)
        observed_s = ", ".join(f"{d.get('name')} {d.get('size_gb')} GB {d.get('type')}" for d in disks) or "none"
        missing = []
        pool = list(disks)
        for want in exp:
            for _ in range(want["count"]):
                match = next((d for d in pool if d.get("type") == want["type"] and d.get("size_gb")
                              and abs(d["size_gb"] - want["size_gb"]) <= want["size_gb"] * 0.02), None)
                if match:
                    pool.remove(match)
                else:
                    missing.append(f"{want['size_gb']} GB {want['type']}")
        ok = not missing
        return CheckOutcome("PASS" if ok else "FAIL", exp_s, observed_s, "GB",
                            "" if ok else "Missing: " + ", ".join(missing), "lsblk -d -o NAME,SIZE,ROTA,TRAN,MODEL", out,
                            [] if ok else ["Locate missing drives or open a vendor discrepancy."])


class DiskHealth(Check):
    key, name = "disk_health", "Disk health evidence (SMART / NVMe log)"
    description = "Every drive reports a passing SMART overall-health or NVMe critical warning = 0."

    def run(self, expected, obs):
        dh, why = _section(obs, "disk_health")
        if dh is None:
            return _unsupported(why + ". Disk health requires smartctl or nvme-cli with root privileges.")
        out = "\n".join(f"{d.get('name')}: smart_passed={d.get('smart_passed')} media_errors={d.get('media_errors')} "
                        f"percentage_used={d.get('percentage_used')}" for d in dh)
        unknown = [d["name"] for d in dh if d.get("smart_passed") is None]
        bad = [d["name"] for d in dh if d.get("smart_passed") is False or (d.get("media_errors") or 0) > 0]
        if bad:
            return CheckOutcome("FAIL", "all drives healthy", f"unhealthy: {', '.join(bad)}", None, "Drive health failure reported.",
                                "smartctl -H / nvme smart-log", out, ["Quarantine drive and open RMA."])
        if unknown:
            return CheckOutcome("MANUAL_REVIEW", "all drives healthy", f"health unknown: {', '.join(unknown)}", None,
                                "Some drives did not report health.", "smartctl -H", out)
        return CheckOutcome("PASS", "all drives healthy", f"{len(dh)} drive(s) healthy", None, "", "smartctl -H / nvme smart-log", out)


class NicInventory(Check):
    key, name = "nic_inventory", "NIC inventory"
    description = "Number of physical network interfaces equals expected."

    def run(self, expected, obs):
        nics, why = _section(obs, "nics")
        exp = expected["nic_count"]
        if nics is None:
            return _unsupported(why, str(exp), "interfaces")
        out = "\n".join(f"{n.get('name')}  role={n.get('role', 'unknown')}  mac={n.get('mac', '?')}  link={n.get('link')}" for n in nics)
        ok = len(nics) == exp
        return CheckOutcome("PASS" if ok else "FAIL", str(exp), str(len(nics)), "interfaces",
                            "" if ok else "Interface count differs from the expected configuration.", "ip -br link", out,
                            [] if ok else ["Verify NIC/OCP card population against the order."])


class LinkSpeed(Check):
    key, name, version = "link_speed", "Negotiated data link speed", "1.1"
    description = "The data-role interface negotiated at least the expected speed."

    def run(self, expected, obs):
        nics, why = _section(obs, "nics")
        exp = expected["data_link_speed_mbps"]
        if nics is None:
            return _unsupported(why, str(exp), "Mb/s")
        data = [n for n in nics if n.get("role") == "data"]
        out = "\n".join(f"{n.get('name')}: role={n.get('role')} speed={n.get('speed_mbps')} Mb/s link={n.get('link')} "
                        f"module={n.get('module', 'n/a')}" for n in nics)
        if not data:
            return CheckOutcome("MANUAL_REVIEW", str(exp), "No interface tagged as data", "Mb/s",
                                "Cannot determine which interface is the data link; tag it in the intake or collector.", "ethtool", out)
        n = data[0]
        sp = n.get("speed_mbps")
        if sp is None or not n.get("link"):
            return CheckOutcome("FAIL", str(exp), "Unknown (no link)", "Mb/s", f"{n['name']} has no link.", f"ethtool {n['name']}", out,
                                ["Check cabling and switch port before re-test."])
        ok = sp >= exp
        return CheckOutcome("PASS" if ok else "FAIL", str(exp), str(sp), "Mb/s",
                            "" if ok else f"{n['name']} negotiated {sp} Mb/s; {exp} Mb/s required. "
                                         f"Common causes: 1G-only transceiver, wrong cable type, or switch port speed setting.",
                            f"ethtool {n['name']}", out,
                            [] if ok else ["Inspect the transceiver part number (ethtool -m) and the switch port configuration, then re-test."])


class Connectivity(Check):
    key, name = "connectivity", "Basic connectivity"
    description = "The default gateway on the provisioning network answers ICMP."

    def run(self, expected, obs):
        c, why = _section(obs, "connectivity")
        if c is None:
            return _unsupported(why, "gateway reachable")
        ok = c.get("gateway_reachable")
        out = f"target: {c.get('target')}\nreachable: {ok}\nrtt_ms: {c.get('rtt_ms')}"
        if ok is None:
            return CheckOutcome("MANUAL_REVIEW", "gateway reachable", "Unknown", None, "Reachability not determined.", "ping -c 3", out)
        return CheckOutcome("PASS" if ok else "FAIL", "gateway reachable", "reachable" if ok else "unreachable", None,
                            "" if ok else "Gateway did not respond.", f"ping -c 3 {c.get('target')}", out)


_KERNEL_FAIL = re.compile(r"(uncorrect|fatal|I/O error|hardware error.*fatal|Machine check.*Uncorrected)", re.I)
_KERNEL_REVIEW = re.compile(r"(corrected|AER|EDAC|mce:|link is not ready|timeout)", re.I)


class KernelErrors(Check):
    key, name = "kernel_errors", "Relevant kernel errors"
    description = "Kernel ring buffer has no uncorrectable hardware errors; corrected errors require review."

    def run(self, expected, obs):
        k, why = _section(obs, "kernel_errors")
        if k is None:
            return _unsupported(why + ". Reading dmesg may require root (kernel.dmesg_restrict).")
        lines = k.get("lines", [])
        fatal = [l for l in lines if _KERNEL_FAIL.search(l)]
        review = [l for l in lines if _KERNEL_REVIEW.search(l) and l not in fatal]
        out = "\n".join(lines) if lines else "(no matching lines)"
        if fatal:
            return CheckOutcome("FAIL", "0 uncorrectable", f"{len(fatal)} uncorrectable", "lines", "Uncorrectable hardware errors in kernel log.",
                                "dmesg --level=err,crit,alert,emerg", out, ["Escalate to the hardware vendor with the logs."])
        if review:
            return CheckOutcome("MANUAL_REVIEW", "0 relevant", f"{len(review)} to review", "lines", "Corrected or link-related messages present.",
                                "dmesg --level=warn,err", out)
        return CheckOutcome("PASS", "0 relevant", "0", "lines", "", "dmesg --level=warn,err", out)


class RedfishHealth(Check):
    key, name = "redfish_health", "BMC health (Redfish)"
    description = "System and chassis health rollup reported by the BMC through Redfish."

    def run(self, expected, obs):
        r, why = _section(obs, "redfish")
        if r is None:
            return _unsupported(why)
        h = r.get("system_health")
        out = "\n".join(f"{k}: {v}" for k, v in r.items())
        if h is None:
            return CheckOutcome("UNSUPPORTED", "OK", "Not reported", None, "BMC did not report Status.HealthRollup.", "GET /redfish/v1/Systems/1", out)
        return CheckOutcome("PASS" if h == "OK" else ("MANUAL_REVIEW" if h == "Warning" else "FAIL"), "OK", h, None,
                            "" if h == "OK" else f"BMC reports {h}.", "GET /redfish/v1/Systems/1", out)


REGISTRY: dict[str, Check] = {c.key: c for c in (
    HardwareIdentity(), CpuInventory(), MemoryCapacity(), StorageInventory(), DiskHealth(), NicInventory(),
    LinkSpeed(), Connectivity(), KernelErrors(), RedfishHealth(),
)}


def disposition(results: list[dict]) -> str:
    """Explicit rules:
    * any required FAIL → FAIL
    * any required UNSUPPORTED / SKIPPED / ERROR / unresolved MANUAL_REVIEW → MANUAL_REVIEW
    * otherwise PASS
    Optional checks never change the disposition but remain visible.
    """
    req = [r for r in results if r["required"]]
    if any(r["result"] == "FAIL" for r in req):
        return "FAIL"
    if any(r["result"] in ("UNSUPPORTED", "SKIPPED", "ERROR", "MANUAL_REVIEW") for r in req):
        return "MANUAL_REVIEW"
    return "PASS"


def effective_disposition(results: list[dict], manual_reviews: dict) -> str:
    """Disposition after recorded manual-review decisions (results themselves stay immutable)."""
    base = disposition(results)
    if base != "MANUAL_REVIEW":
        return base
    req_review = [r for r in results if r["required"] and r["result"] in ("UNSUPPORTED", "SKIPPED", "ERROR", "MANUAL_REVIEW")]
    decisions = [manual_reviews.get(r["check_key"], {}).get("decision") for r in req_review]
    if any(d == "reject" for d in decisions):
        return "FAIL"
    if all(d == "accept" for d in decisions):
        return "PASS"
    return "MANUAL_REVIEW"
