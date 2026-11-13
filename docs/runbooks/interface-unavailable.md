# Runbook: Network interface unavailable

| | |
|---|---|
| Version | 1.3 (matches the `interface-unavailable` seed runbook) |
| Lab scenario | `nic-down` (lab-srv-01 `eth1` ↔ lab-sw-01 `Eth1/7`, cable `CBL-0107`) |
| Ownership | The technician owns the physical layer (cables, optics, seating). Switch configuration belongs to the network team. |

## Symptom

A host is unreachable on one network while other paths, such as management or the BMC, still respond.

## 1. Initial checks

1. **Unreachable does not mean the NIC failed.** List the possible causes before touching hardware: cable or optic, far-end switch port, host configuration, NIC.
2. Check whether other hosts on the same switch or patch panel are affected. Several hosts down points away from this server.
3. Acknowledge the incident.

> Note: in the lab scenario, link-state history is not retained, so **fault onset is unknown** and detection latency is reported as *Unavailable*, not 0.

## 2. Investigation sequence

| # | Step | Example command | Interpretation |
|---|---|---|---|
| 1 | Reachability on every path | `ping -c3 HOST-bmc; ssh HOST true; ping -c3 HOST-data` | If management responds, the host is up and the fault is isolated to one path. |
| 2 | Link state and counters | `ip -s link show eth1; ethtool eth1` | `NO-CARRIER` / `Link detected: no` means no physical signal. `state DOWN` with no `UP` flag is an administrative state. |
| 3 | Switch-side port | `show interface Eth1/7 status` (read-only, or ask the network team) | Both ends without link points to the medium (cable or optics). Only one end down points to that end. |
| 4 | Kernel and networkd log | `journalctl -k --since '-15 min' \| grep -i eth1` | Time of link loss and driver context. |
| 5 | Trace the documented path | RackOps Lab → Racks & cabling → Trace | Confirms which cable and ports to inspect. Uses modeled data only; nothing is inferred. |

## 3. Decision points

- **Both ends down, port not err-disabled.** Inspect and reseat. If that fails, swap the cable for a **tested** spare.
- **Switch port err-disabled or admin-down.** Escalate to network engineering. Do not change switch configuration.
- **Link comes back with a known-good cable on a known-good port, but not on this NIC.** Suspect the NIC or transceiver. Read the optic's DOM (`ethtool -m eth1`) and open a hardware case.

## 4. Corrective action

1. Reseat the connector at the server end, then the switch end. Confirm the link LED.
2. If the link does not return, swap in a tested cable. Record the new cable ID and label both ends.

## 5. Verification

- [ ] Carrier detected (`LOWER_UP`) at the expected speed (10000 Mb/s full duplex)
- [ ] Switch port oper-up
- [ ] Counters increment and the host is reachable on the data path
- [ ] 2 consecutive healthy probes after the repair

## 6. Escalation criteria

- Switch configuration issues: network engineering.
- NIC or transceiver replacement: the hardware workflow (spare reservation, consumption, return record).

## 7. Rollback and recovery considerations

- If a swapped cable also fails, restore the original and label it *suspect*. The fault is probably elsewhere.
- Never pull an unidentified live cable to "trace" it.
