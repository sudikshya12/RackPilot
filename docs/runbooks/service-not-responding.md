# Runbook: Service not responding (health probe failing)

| | |
|---|---|
| Version | 1.2 (matches the `service-not-responding` seed runbook) |
| Lab scenario | `svc-stopped` (lab-srv-02, `inventory-api.service`) |
| Owner of the service | Service owner / on-call engineer. The technician restores and escalates; they do not change application code or configuration. |

## Symptom

An HTTP or TCP health probe for a service fails, for example `connection refused` or a timeout. In the lab, `GET http://lab-srv-02:8080/health` fails on 2 consecutive probes, 3 s apart.

## 1. Initial checks

1. Confirm the alert is current. Look at the last 3 probe results and their timestamps; a single stale failure is not an outage.
2. **Acknowledge** the incident so ownership is visible. Acknowledgment latency is measured from this action.
3. Check for an active change or maintenance window on the host. A planned stop is handled differently from an unplanned one.

## 2. Investigation sequence

| # | Step | Example command | What it tells you |
|---|---|---|---|
| 1 | Distinguish *refused* from *timeout* | `curl -sS -m 3 -i http://HOST:8080/health` | Refused: the host answered and nothing is listening on the port. Timeout: the path or the host is not answering. |
| 2 | Unit state | `systemctl status inventory-api.service --no-pager` | `inactive (dead)`, `failed`, or `active`, plus how the main process exited (signal or exit code). |
| 3 | Journal around the failure | `journalctl -u inventory-api.service --since '-15 min' --no-pager` | An explicit `systemctl stop`, a crash, an OOM kill, or a failed dependency. |
| 4 | Listener check | `ss -ltnp` | Confirms whether anything owns the port. |
| 5 | Rule out the network path | `ip -s link show eth1; ethtool eth1` | Carrier up with incrementing counters argues against a link problem. |

Record each output as evidence. Write down what each output **shows** before deciding what it **means**.

## 3. Decision points

- **Unit inactive after an orderly SIGTERM, with a logged stop command.** This is an intentional or scripted stop. Start the unit and find out who or what stopped it.
- **Unit `failed`, with a non-zero exit or core dump.** This is a crash. Collect the logs first. Allow at most one controlled restart, then escalate to the service owner. Never loop restarts.
- **Unit active but the port is not listening.** This is a configuration or bind problem. Escalate to the service owner.
- **Carrier down or counters frozen.** Switch to the [Interface unavailable](interface-unavailable.md) runbook.

## 4. Corrective action

```bash
sudo systemctl start inventory-api.service
systemctl is-enabled inventory-api.service   # expect: enabled
```

Record who or what stopped the unit (in the lab: `maint-cleanup.sh`, uid 1004) and open a follow-up for the script owner.

## 5. Verification (required before resolving)

- [ ] Unit `active (running)` with a new main PID
- [ ] Port 8080 has a listener
- [ ] `GET /health` returns 200
- [ ] At least **2 consecutive healthy probes after the repair**. A single success is not enough.

In RackOps Lab, the **Resolve** action is rejected until a verification executed after the latest repair has passed.

## 6. Escalation criteria

- Crash loop (more than 1 restart within 10 minutes): service owner or on-call engineer.
- Suspected data corruption: service owner, **before** any restart.
- Several hosts affected at once: incident commander; a shared dependency is likely.

## 7. Rollback and recovery considerations

If starting the unit makes things worse (error storm, load spike), stop it again and escalate. Do not leave a service flapping.
