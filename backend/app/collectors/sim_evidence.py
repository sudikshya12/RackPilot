"""Simulated evidence collectors.

Output is rendered from the simulation state so it stays coherent with probes and metrics.
Each collector returns observed output and an *interpretation of what was observed*.
Diagnosis (hypotheses) is kept separate, in the incident's hypothesis list.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

COLLECTORS: dict[str, dict[str, str]] = {
    "systemctl_status": {"label": "systemctl status", "group": "service"},
    "journalctl": {"label": "journalctl (unit / kernel)", "group": "logs"},
    "filesystem_usage": {"label": "Filesystem utilization (df / du)", "group": "storage"},
    "process_info": {"label": "Process information (ps)", "group": "process"},
    "listening_sockets": {"label": "Listening sockets (ss)", "group": "network"},
    "interface_counters": {"label": "Network interface counters (ip -s link)", "group": "network"},
    "service_reachability": {"label": "Service reachability (mgmt + data)", "group": "network"},
    "http_check": {"label": "HTTP health check", "group": "service"},
    "switch_port": {"label": "Switch port status (modeled)", "group": "network"},
    "redfish_power": {"label": "Redfish Power resource (fixture)", "group": "hardware"},
    "sel_log": {"label": "BMC System Event Log (fixture)", "group": "hardware"},
    "pdu_outlet": {"label": "PDU outlet status (modeled)", "group": "power"},
}


def _ts(t: datetime) -> str:
    return t.strftime("%b %d %H:%M:%S")


def _long(t: datetime) -> str:
    return t.strftime("%a %Y-%m-%d %H:%M:%S UTC")


def collect(collector: str, state: dict[str, Any], now: datetime, fault_at: datetime | None) -> dict[str, Any]:
    fn = _REGISTRY.get(collector)
    if fn is None:
        raise KeyError(collector)
    host = state["host"]
    out = fn(state, now, fault_at or now - timedelta(seconds=30), host)
    out.setdefault("limitations", "Simulated output rendered from scenario state; not collected from hardware.")
    return out


def _systemctl(s, now, f, host):
    svc = s["service"]
    if svc["active"]:
        out = (
            f"● {svc['unit']} - Inventory API (lab test service)\n"
            f"     Loaded: loaded (/etc/systemd/system/{svc['unit']}; enabled; preset: disabled)\n"
            f"     Active: active (running) since {_long(now - timedelta(seconds=40))}; 40s ago\n"
            f"   Main PID: {svc['pid']} (serve)\n"
            f"      Tasks: 9 (limit: 38216)\n"
            f"     Memory: 61.4M\n"
            f"        CPU: 1.204s\n"
            f"     CGroup: /system.slice/{svc['unit']}\n"
            f"             └─{svc['pid']} /opt/inventory-api/bin/serve --port {svc['port']}"
        )
        interp = f"Unit is loaded, enabled and active (running) with main PID {svc['pid']}."
        obs = {"unit_state": "active", "sub_state": "running", "enabled": True, "main_pid": svc["pid"]}
    else:
        out = (
            f"○ {svc['unit']} - Inventory API (lab test service)\n"
            f"     Loaded: loaded (/etc/systemd/system/{svc['unit']}; enabled; preset: disabled)\n"
            f"     Active: inactive (dead) since {_long(f)}\n"
            f"   Duration: 3h 12min 4.211s\n"
            f"    Process: {svc['pid']} ExecStart=/opt/inventory-api/bin/serve --port {svc['port']} (code=killed, signal=TERM)\n"
            f"   Main PID: {svc['pid']} (code=killed, signal=TERM)\n"
            f"        CPU: 41.882s"
        )
        interp = (
            "Unit is enabled but inactive (dead). The main process ended on SIGTERM, which is consistent with an "
            "orderly stop request rather than a crash (no non-zero exit code, no core dump)."
        )
        obs = {"unit_state": "inactive", "sub_state": "dead", "enabled": True, "exit": "signal=TERM"}
    return {"command": f"systemctl status {svc['unit']} --no-pager", "output": out, "observations": obs, "interpretation": interp}


def _journal(s, now, f, host):
    svc = s["service"]
    lines = []
    if s["service"]["stopped_by"] or (not svc["active"]):
        lines += [
            f"{_ts(f - timedelta(seconds=2))} {host} sudo[9921]: maint-cleanup : TTY=unknown ; PWD=/opt/maint ; USER=root ; COMMAND=/usr/bin/systemctl stop {svc['unit']}",
            f"{_ts(f)} {host} systemd[1]: Stopping {svc['unit']} - Inventory API (lab test service)...",
            f"{_ts(f)} {host} serve[{svc['pid']}]: received SIGTERM, draining 0 connections",
            f"{_ts(f)} {host} systemd[1]: {svc['unit']}: Deactivated successfully.",
            f"{_ts(f)} {host} systemd[1]: Stopped {svc['unit']} - Inventory API (lab test service).",
        ]
    if s["fs"]["used_gib"] >= s["fs"]["size_gib"] * 0.95 and not s["fs"].get("cleaned"):
        lines += [
            f"{_ts(f + timedelta(seconds=4))} {host} batch-export[5512]: write /srv/scratch/logs/export-debug.log.14: no space left on device",
            f"{_ts(f + timedelta(seconds=7))} {host} serve[{svc['pid']}]: ERROR cache flush failed: [Errno 28] No space left on device",
        ]
    if s["cpu"]["runaway"]:
        lines += [
            f"{_ts(f)} {host} systemd[1]: Started batch-reindex.service - Lab batch reindex (test harness).",
            f"{_ts(f + timedelta(seconds=1))} {host} batch-reindex[7730]: spawning 32 workers (parallelism=unbounded)",
            f"{_ts(f + timedelta(seconds=9))} {host} serve[{svc['pid']}]: WARN request latency p95=1184ms exceeds 500ms",
        ]
    if not s["iface"]["carrier"]:
        lines += [
            f"{_ts(f)} {host} kernel: mlx5_core 0000:41:00.1 eth1: Link down",
            f"{_ts(f)} {host} systemd-networkd[812]: eth1: Lost carrier",
        ]
    if s["psu"]["PSU2"] != "OK":
        lines += [f"{_ts(f)} {host} ipmievd[655]: Power Supply PSU2 Failure detected Asserted"]
    for r in s["repairs"]:
        lines.append(f"{_ts(now - timedelta(seconds=5))} {host} lab-sim: operator action recorded: {r}")
    if not lines:
        lines = [f"{_ts(now - timedelta(seconds=60))} {host} systemd[1]: Started {svc['unit']} - Inventory API (lab test service).",
                 "-- No entries indicating failure in the selected window --"]
    interp = "Log lines are reproduced verbatim; see hypothesis list for what they may indicate."
    if not svc["active"]:
        interp = (f"The journal shows an explicit `systemctl stop` issued via sudo by user maint-cleanup a few seconds "
                  f"before the unit stopped. No crash or OOM messages are present.")
    elif s["cpu"]["runaway"]:
        interp = "A test-harness job (batch-reindex) started with unbounded parallelism shortly before latency warnings."
    elif not s["iface"]["carrier"]:
        interp = "Kernel reports link down on eth1 and networkd reports lost carrier. This identifies loss of physical-layer signal, not its cause."
    elif s["fs"]["used_gib"] >= s["fs"]["size_gib"] * 0.95 and not s["fs"].get("cleaned"):
        interp = "Two processes report ENOSPC (errno 28) on /srv/scratch."
    return {"command": f"journalctl -u {svc['unit']} -k --since '-15 min' --no-pager", "output": "\n".join(lines),
            "observations": {"line_count": len(lines)}, "interpretation": interp,
            "limitations": "Simulated journal excerpt; only lines relevant to the scenario are rendered. Sanitized: no secrets present."}


def _df(s, now, f, host):
    fs = s["fs"]
    used, size = fs["used_gib"], fs["size_gib"]
    pct = round(100 * used / size)
    avail = round(size - used, 1)
    out = (
        "Filesystem      Size  Used Avail Use% Mounted on\n"
        "/dev/nvme0n1p2  220G   41G  168G  20% /\n"
        f"{fs['device']}   {size:.0f}G   {used:.1f}G  {avail:.1f}G  {pct}% {fs['mount']}\n\n"
        f"$ du -xh --max-depth=2 {fs['mount']} | sort -rh | head -4\n"
    )
    if pct >= 90 and not fs.get("cleaned"):
        out += f"{used:.1f}G\t{fs['mount']}\n{used - 3.1:.1f}G\t{fs['mount']}/logs\n2.4G\t{fs['mount']}/cache\n0.7G\t{fs['mount']}/tmp"
        interp = f"{fs['mount']} is at {pct}% with {avail} GiB free; {fs['mount']}/logs holds most of the used space."
    else:
        out += f"{used:.1f}G\t{fs['mount']}\n8.1G\t{fs['mount']}/cache\n{max(used - 10.2, 0.4):.1f}G\t{fs['mount']}/logs\n0.7G\t{fs['mount']}/tmp"
        interp = f"{fs['mount']} is at {pct}% utilization."
    return {"command": f"df -h / {fs['mount']} && du -xh --max-depth=2 {fs['mount']}", "output": out,
            "observations": {"mount": fs["mount"], "used_pct": pct, "avail_gib": avail}, "interpretation": interp}


def _ps(s, now, f, host):
    svc = s["service"]
    rows = ["    PID USER       %CPU %MEM     ELAPSED CMD"]
    if s["cpu"]["runaway"]:
        rows.append("   7730 labjobs   3104  6.2       01:12 /opt/lab/bin/batch-reindex --workers 32")
    if svc["active"]:
        rows.append(f"   {svc['pid']} svc-inv     {'41' if s['cpu']['runaway'] else '3.1'}  0.2       40:00 /opt/inventory-api/bin/serve --port {svc['port']}")
    rows += ["    812 systemd+    0.1  0.0  9-04:12:33 /usr/lib/systemd/systemd-networkd",
             "    655 root        0.0  0.0  9-04:12:35 /usr/sbin/ipmievd sel"]
    if s["cpu"]["runaway"]:
        interp = "batch-reindex (PID 7730) uses ~3100 % CPU, about 31 of 32 cores. inventory-api is a minor consumer."
    elif not svc["active"]:
        interp = "No inventory-api (serve) process is present in the process table."
    else:
        interp = "No process is consuming abnormal CPU. inventory-api is running."
    return {"command": "ps -eo pid,user,%cpu,%mem,etime,cmd --sort=-%cpu | head", "output": "\n".join(rows),
            "observations": {"serve_running": svc["active"], "runaway_pid": 7730 if s["cpu"]["runaway"] else None},
            "interpretation": interp}


def _ss(s, now, f, host):
    svc = s["service"]
    rows = ["State  Recv-Q Send-Q Local Address:Port Peer Address:Port Process",
            "LISTEN 0      128          0.0.0.0:22        0.0.0.0:*     users:((\"sshd\",pid=901,fd=3))",
            "LISTEN 0      4096       127.0.0.1:9100      0.0.0.0:*     users:((\"node_exporter\",pid=944,fd=3))"]
    if svc["active"]:
        rows.append(f"LISTEN 0      511          0.0.0.0:{svc['port']}      0.0.0.0:*     users:((\"serve\",pid={svc['pid']},fd=7))")
    interp = (f"TCP {svc['port']} has a listener owned by serve (PID {svc['pid']})." if svc["active"]
              else f"No process is listening on TCP {svc['port']}; sshd (22) and node_exporter (9100) are listening normally.")
    return {"command": "ss -ltnp", "output": "\n".join(rows), "observations": {"port_8080_listening": svc["active"]}, "interpretation": interp}


def _iplink(s, now, f, host):
    i = s["iface"]
    n = s.get("probe", 0)
    rx, tx = 88_412_903 + n * 5400, 61_990_221 + n * 4100
    flags = "<BROADCAST,MULTICAST,UP,LOWER_UP>" if i["carrier"] else "<NO-CARRIER,BROADCAST,MULTICAST,UP>"
    state = "UP" if i["carrier"] else "DOWN"
    out = (
        f"3: {i['name']}: {flags} mtu 9000 qdisc mq state {state} mode DEFAULT group default qlen 1000\n"
        f"    link/ether 02:00:5e:10:00:{'21' if host.endswith('01') else '22'} brd ff:ff:ff:ff:ff:ff\n"
        f"    RX:  bytes packets errors dropped  missed   mcast\n"
        f"    {rx * 900:>14} {rx:>9}      0       0       0     112\n"
        f"    TX:  bytes packets errors dropped carrier collsns\n"
        f"    {tx * 880:>14} {tx:>9}      0       0 {'      3' if not i['carrier'] else '      0'}       0\n\n"
        f"$ ethtool {i['name']} | grep -E 'Speed|Duplex|Link detected'\n"
        + (f"\tSpeed: {i['speed_mbps']}Mb/s\n\tDuplex: Full\n\tLink detected: yes" if i["carrier"]
           else "\tSpeed: Unknown!\n\tDuplex: Unknown! (255)\n\tLink detected: no")
    )
    interp = (f"{i['name']} is administratively UP with carrier at {i['speed_mbps']} Mb/s; counters increment between samples; no errors."
              if i["carrier"] else
              f"{i['name']} is administratively UP but reports NO-CARRIER and 'Link detected: no'. The OS has the interface enabled "
              "but sees no physical-layer signal. This alone does not identify whether the cable, the far-end port, or the NIC is at fault.")
    return {"command": f"ip -s link show {i['name']} && ethtool {i['name']}", "output": out,
            "observations": {"carrier": i["carrier"], "admin_up": True, "speed_mbps": i["speed_mbps"] if i["carrier"] else None},
            "interpretation": interp}


def _reach(s, now, f, host):
    i, svc = s["iface"], s["service"]
    out = (
        f"mgmt  {host}-bmc (192.0.2.{'11' if host.endswith('01') else '12'})  ICMP: reply 0.41 ms\n"
        f"mgmt  {host} eno1 (198.51.100.{'21' if host.endswith('01') else '22'}) SSH  : banner OK\n"
        f"data  {host} eth1 (203.0.113.{'21' if host.endswith('01') else '22'}) ICMP: {'reply 0.18 ms' if i['carrier'] else 'timeout (3/3 lost)'}\n"
        f"data  {host}:{svc['port']}  TCP  : {'connected' if (i['carrier'] and svc['active']) else ('refused' if i['carrier'] else 'timeout')}"
    )
    if not i["carrier"]:
        interp = "Management paths respond; only the data-network path (eth1) is unreachable. The host is up and the fault is isolated to the eth1 path."
    elif not svc["active"]:
        interp = "The host responds on both management and data networks; the TCP port refuses connections. The network path works."
    else:
        interp = "All management and data paths respond."
    return {"command": "lab-reach --host " + host + " (ICMP + TCP connect, modeled addresses)", "output": out,
            "observations": {"mgmt_ok": True, "data_icmp_ok": i["carrier"], "tcp_ok": i["carrier"] and svc["active"]},
            "interpretation": interp,
            "limitations": "Simulated. Addresses are RFC 5737 documentation ranges."}


def _http(s, now, f, host):
    svc, i = s["service"], s["iface"]
    if not i["carrier"]:
        out, ok = f"curl: (28) Connection timed out after 3001 milliseconds", False
    elif not svc["active"]:
        out, ok = f"curl: (7) Failed to connect to {host} port {svc['port']} after 1 ms: Connection refused", False
    elif s["cpu"]["runaway"]:
        out, ok = 'HTTP/1.1 200 OK\ncontent-type: application/json\n\n{"status":"ok"}\n-- time_total: 1.212s', True
    else:
        out, ok = 'HTTP/1.1 200 OK\ncontent-type: application/json\n\n{"status":"ok"}\n-- time_total: 0.042s', True
    interp = ("Connection refused means the host answered but nothing accepted the connection on that port."
              if (i["carrier"] and not svc["active"]) else
              ("Timeout means no answer was received at all." if not i["carrier"] else
               ("Health endpoint responded 200 but slowly (>1 s)." if s["cpu"]["runaway"] else "Health endpoint responded 200 within normal latency.")))
    return {"command": f"curl -sS -m 3 -i http://{host}:{svc['port']}/health", "output": out,
            "observations": {"http_ok": ok}, "interpretation": interp}


def _switch(s, now, f, host):
    i = s["iface"]
    up = i["carrier"]
    out = (f"Port      Name              Status       Vlan  Duplex Speed Type\n"
           f"Eth1/7    {host}-eth1     {'connected' if up else 'notconnect'}   210   {'full' if up else 'auto'}   {'10G' if up else 'auto'}  10Gbase-SR\n\n"
           f"Eth1/7 is {'up' if up else 'down (Link not connected)'}, admin state is up\n"
           f"  Last link flapped {'9d 04h' if up else '00:01:12'}\n  Error-disabled: no")
    interp = ("Switch port is admin up, not error-disabled, and has no link. Both ends see no signal, which points to the physical path between them (cable/optics)."
              if not up else "Switch port is connected at 10G.")
    return {"command": "show interface Eth1/7 status (modeled switch lab-sw-01)", "output": out,
            "observations": {"port_up": up, "err_disabled": False}, "interpretation": interp,
            "limitations": "Modeled switch output. In a real facility switch configuration belongs to the network team; the technician reads it but does not change it."}


def _redfish_power(s, now, f, host):
    p = s["psu"]
    import json
    doc = {
        "@odata.id": "/redfish/v1/Chassis/1/Power",
        "PowerSupplies": [
            {"MemberId": "0", "Name": "PSU1", "Model": "NL-PSU-800P", "SerialNumber": "SIM-PSU-04A-0007",
             "PowerOutputWatts": 212 if p["PSU2"] == "OK" else 398, "LineInputVoltage": 230,
             "Status": {"State": "Enabled", "Health": p["PSU1"]}},
            {"MemberId": "1", "Name": "PSU2", "Model": "NL-PSU-800P", "SerialNumber": "SIM-PSU-04B-0008" if p["PSU2"] != "OK" or not s["repairs"] else "SIM-PSU-SP-0103",
             "PowerOutputWatts": 206 if p["PSU2"] == "OK" else None, "LineInputVoltage": 230 if p["PSU2"] == "OK" else None,
             "Status": {"State": "Enabled" if p["PSU2"] == "OK" else "UnavailableOffline", "Health": p["PSU2"]}},
        ],
        "Redundancy": [{"Name": "PSU Redundancy", "Mode": "N+m", "Status": {"Health": "OK" if p["PSU2"] == "OK" else "Critical"},
                        "RedundancySet@odata.count": 2, "MinNumNeeded": 1}],
    }
    interp = ("PSU2 reports Health=Critical and State=UnavailableOffline with no output; PSU1 carries the full load (398 W modeled). "
              "Redundancy is lost." if p["PSU2"] != "OK" else "Both PSUs report Health=OK and share the load; redundancy is reported OK.")
    return {"command": "GET /redfish/v1/Chassis/1/Power (fixture)", "output": json.dumps(doc, indent=2),
            "observations": {"psu1": p["PSU1"], "psu2": p["PSU2"]}, "interpretation": interp,
            "limitations": "Fixture shaped like a DMTF Redfish Power resource. Real BMCs differ in which properties they populate."}


def _sel(s, now, f, host):
    lines = ["   1 | 11/09/2026 | 08:14:02 | System Boot Initiated | Initiated by power up | Asserted"]
    if s["psu"]["PSU2"] != "OK" or s["repairs"]:
        lines.append(f"   2 | {f.strftime('%m/%d/%Y')} | {f.strftime('%H:%M:%S')} | Power Supply PSU2 | Failure detected | Asserted")
        lines.append(f"   3 | {f.strftime('%m/%d/%Y')} | {f.strftime('%H:%M:%S')} | Power Supply PSU Redundancy | Redundancy Lost | Asserted")
    if s["psu"]["PSU2"] == "OK" and s["repairs"]:
        lines.append(f"   4 | {now.strftime('%m/%d/%Y')} | {now.strftime('%H:%M:%S')} | Power Supply PSU2 | Presence detected | Asserted")
        lines.append(f"   5 | {now.strftime('%m/%d/%Y')} | {now.strftime('%H:%M:%S')} | Power Supply PSU Redundancy | Fully Redundant | Asserted")
    return {"command": "ipmitool sel list (fixture)", "output": "\n".join(lines), "observations": {"entries": len(lines)},
            "interpretation": "SEL records PSU2 failure and redundancy loss at the same timestamp." if s["psu"]["PSU2"] != "OK"
            else "SEL shows the failure followed by presence detection and restored redundancy.",
            "limitations": "Fixture. SEL timestamps on real BMCs depend on BMC clock accuracy."}


def _pdu(s, now, f, host):
    out = ("Outlet            Device           Feed     State  Current(A, estimate)\n"
           "nl-r01-pdu-b/B04  lab-srv-04 PSU2  FEED-B   ON     " + ("0.0" if s["psu"]["PSU2"] != "OK" else "0.9") + "\n"
           "nl-r01-pdu-b/B03  lab-srv-01 PSU2  FEED-B   ON     0.9\n"
           "nl-r01-pdu-b/B02  lab-srv-02 PSU2  FEED-B   ON     0.9\n"
           "nl-r01-pdu-b/B08  lab-sw-01 PSU2   FEED-B   ON     0.4")
    return {"command": "PDU outlet view (modeled documentation)", "output": out, "observations": {"outlet_on": True},
            "interpretation": "The outlet feeding PSU2 is ON and neighbouring FEED-B loads draw current. The feed is present, so feed loss is unlikely.",
            "limitations": "Modeled PDU documentation, not a metered reading. Currents are estimates."}


_REGISTRY = {
    "systemctl_status": _systemctl,
    "journalctl": _journal,
    "filesystem_usage": _df,
    "process_info": _ps,
    "listening_sockets": _ss,
    "interface_counters": _iplink,
    "service_reachability": _reach,
    "http_check": _http,
    "switch_port": _switch,
    "redfish_power": _redfish_power,
    "sel_log": _sel,
    "pdu_outlet": _pdu,
}
