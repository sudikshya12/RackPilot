"""Read-only Redfish adapter.

Only HTTP GET is implemented. No power control, firmware update, or any other mutating
action exists in this module (by design, and asserted in tests).

Modes
-----
* fixture (default): reads DMTF-style JSON from ``app/fixtures/redfish``. Those files are
  hand-written in the shape of the DMTF Redfish mockups and are labeled IMPORTED_SAMPLE.
* live: set RACKOPS_REDFISH_URL / _USERNAME / _PASSWORD. TLS verification is on by default.

Real BMCs populate different subsets of properties, so every accessor tolerates missing keys.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import httpx

from ..config import get_settings

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "redfish"


class RedfishError(Exception):
    pass


class RedfishClient:
    def __init__(self, base_url: Optional[str] = None, username: str = "", password: str = "",
                 verify_tls: bool = True, timeout: float = 5.0):
        self.base_url = (base_url or "").rstrip("/")
        self.mode = "live" if self.base_url else "fixture"
        self._auth = (username, password) if username else None
        self._verify = verify_tls
        self._timeout = timeout

    @classmethod
    def from_settings(cls) -> "RedfishClient":
        s = get_settings()
        return cls(s.redfish_url, s.redfish_username, s.redfish_password, s.redfish_verify_tls, s.redfish_timeout_seconds)

    def get(self, path: str) -> dict[str, Any]:
        if not path.startswith("/redfish/v1"):
            raise RedfishError("Only /redfish/v1 resources may be read")
        if self.mode == "fixture":
            f = FIXTURE_DIR / (path.strip("/").replace("/", "__") + ".json")
            if not f.exists():
                raise RedfishError(f"Fixture not available for {path}")
            return json.loads(f.read_text())
        try:
            r = httpx.get(self.base_url + path, auth=self._auth, verify=self._verify, timeout=self._timeout,
                          headers={"Accept": "application/json"})
        except httpx.HTTPError as e:
            raise RedfishError(f"{type(e).__name__}: {e}") from e
        if r.status_code != 200:
            raise RedfishError(f"GET {path} returned HTTP {r.status_code}")
        return r.json()

    def describe(self) -> dict[str, Any]:
        return {"mode": self.mode, "base_url": self.base_url or None, "verify_tls": self._verify,
                "authenticated": bool(self._auth)}  # never return credentials


def _members(client: RedfishClient, coll: dict) -> list[dict]:
    out = []
    for m in coll.get("Members", []):
        try:
            out.append(client.get(m["@odata.id"]))
        except (RedfishError, KeyError):
            continue
    return out


def collect_observations(client: RedfishClient, system_path: str = "/redfish/v1/Systems/1") -> dict[str, Any]:
    """Map selected Redfish resources to the acceptance observation schema. Missing → unsupported."""
    obs: dict[str, Any] = {}
    try:
        sysr = client.get(system_path)
    except RedfishError as e:
        return {"_meta": {"collector": f"redfish_{client.mode}", "error": str(e)}}
    obs["identity"] = {"serial_number": sysr.get("SerialNumber"), "manufacturer": sysr.get("Manufacturer"),
                       "model": sysr.get("Model"), "bios_version": sysr.get("BiosVersion")}
    ps = sysr.get("ProcessorSummary") or {}
    obs["cpu"] = {"count": ps.get("Count"), "model": ps.get("Model"), "cores_total": ps.get("CoreCount")} if ps else {"_unsupported": "ProcessorSummary not present"}
    ms = sysr.get("MemorySummary") or {}
    if ms.get("TotalSystemMemoryGiB") is not None:
        obs["memory"] = {"total_gib": float(ms["TotalSystemMemoryGiB"]), "basis": "dimm_inventory", "dimms": []}
        try:
            for d in _members(client, client.get(system_path + "/Memory")):
                if d.get("Status", {}).get("State") == "Absent":
                    continue
                mib = d.get("CapacityMiB")
                obs["memory"]["dimms"].append({"slot": d.get("DeviceLocator") or d.get("Id"),
                                               "size_gib": round(mib / 1024, 1) if mib else None,
                                               "type": d.get("MemoryDeviceType", "")})
        except RedfishError:
            pass
    else:
        obs["memory"] = {"_unsupported": "MemorySummary.TotalSystemMemoryGiB not present"}
    try:
        nics = []
        for e in _members(client, client.get(system_path + "/EthernetInterfaces")):
            nics.append({"name": e.get("Id"), "mac": e.get("MACAddress"), "speed_mbps": e.get("SpeedMbps"),
                         "link": (e.get("LinkStatus") == "LinkUp") if e.get("LinkStatus") else None,
                         "role": (e.get("Oem") or {}).get("RackOpsRole", "unknown")})
        obs["nics"] = nics
    except RedfishError as e:
        obs["nics"] = {"_unsupported": f"EthernetInterfaces unavailable: {e}"}
    try:
        drives = []
        for st in _members(client, client.get(system_path + "/Storage")):
            for dref in st.get("Drives", []):
                try:
                    d = client.get(dref["@odata.id"])
                except RedfishError:
                    continue
                cap = d.get("CapacityBytes")
                drives.append({"name": d.get("Id"), "size_gb": round(cap / 1e9) if cap else None,
                               "type": (d.get("Protocol") or d.get("MediaType") or "").lower().replace("ssd", "ssd"),
                               "model": d.get("Model", ""),
                               "health": (d.get("Status") or {}).get("Health")})
        obs["storage"] = drives
        obs["disk_health"] = {"_unsupported": "Redfish Drive.Status is not equivalent to SMART/NVMe health logs"}
    except RedfishError as e:
        obs["storage"] = {"_unsupported": f"Storage unavailable: {e}"}
    status = sysr.get("Status") or {}
    obs["redfish"] = {"system_health": status.get("HealthRollup") or status.get("Health"),
                      "power_state": sysr.get("PowerState"), "mode": client.mode}
    obs["connectivity"] = {"_unsupported": "Redfish does not report host data-network reachability"}
    obs["kernel_errors"] = {"_unsupported": "Redfish does not expose the host kernel log"}
    obs["_meta"] = {"collector": f"redfish_{client.mode}", "system_path": system_path}
    return obs
