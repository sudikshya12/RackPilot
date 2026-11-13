# Runbook: Failed power supply replacement

| | |
|---|---|
| Version | 1.1 (matches the `psu-replacement` seed runbook) |
| Lab scenario | `psu-failure` (lab-srv-04, PSU2 `NL-AST-P04B`, serial `SIM-PSU-04B-0008`) |
| Spare | `NL-PSU-800P`, listed compatible with `NL-1U-Compute` and `NL-2U-Storage` |

## Symptom

The BMC reports a PSU fault and power redundancy is lost. The server stays up on its remaining PSU.

## 1. Initial checks

1. Confirm **which** PSU has failed, from both the BMC health and the SEL.
2. Confirm the server is running on the remaining PSU and that PSU is healthy. If the surviving PSU is also degraded, treat it as urgent and escalate.
3. Acknowledge the incident.

## 2. Investigation sequence

| # | Step | Example (read-only) | Interpretation |
|---|---|---|---|
| 1 | PSU status from the BMC | `curl -s -u USER https://BMC/redfish/v1/Chassis/1/Power` | Per-PSU `Status.Health`, `LineInputVoltage`, output watts, redundancy state. |
| 2 | System Event Log | `ipmitool sel list` | Timestamped "Power Supply PSU2 Failure detected" and "Redundancy Lost". |
| 3 | Outlet and feed | PDU outlet view / documentation | Outlet ON and other loads on the same feed healthy means the feed is present. |

## 3. Decision points

- **Feed present, other loads on the feed healthy, PSU reports a fault.** Replace the PSU.
- **Feed absent.** This is a facility power issue. Escalate to facilities. Do **not** swap PSUs.
- **No compatible spare in stock.** A reviewed compatibility exception (named reviewer and justification) is the only alternative. Otherwise order a part.

## 4. Corrective action (records and physical work)

1. **Find a compatible spare** (Spare parts, filtered by device). Incompatible parts are flagged.
2. **Reserve it** against the incident. Available stock drops; on-hand stock does not change.
3. Hot-swap the PSU per the platform guide. Wear ESD protection and keep the cord retention clip on.
4. **Record the replacement serial and consume the reservation.** In RackOps Lab, one transaction:
   - writes a `consume` ledger row of −1,
   - marks the reservation consumed,
   - records the new PSU as an installed asset on PSU2,
   - quarantines the failed unit,
   - records the repair on the incident.
5. **Open a return record** with the failure evidence. The failed unit moves to *pending return*. Enter the vendor's return reference when it is issued; RackOps Lab does not contact the vendor.

## 5. Verification

- [ ] PSU2 `Status.Health = OK`
- [ ] Redundancy restored
- [ ] Both PSUs report input voltage
- [ ] Healthy polls after the repair

## 6. Escalation criteria

- Repeated PSU failures on the same chassis: hardware vendor (possible backplane or PSU cage fault).
- Feed or PDU problems: facilities / electrical.

## 7. Rollback and recovery considerations

If the new PSU does not come up, reseat it. If it still fails, release or record the outcome, quarantine that unit too, and escalate. Do not consume a second spare without understanding why the first one failed.
