# What the Candidate Should Understand

Read this before presenting. These are the concepts an interviewer is most likely to probe.

## How detection works

- A **probe** is a periodic check, for example `GET /health` every 3 s. A **detection rule** turns probe results into an incident; here, *2 consecutive failures*.
- **Fault onset** is when the problem started. **Detection** is when the rule fired. They differ by up to the probe interval multiplied by the number of failures required.
- Requiring 2 failures avoids alerting on a single dropped probe, at the cost of one extra interval of latency.
- If onset is unknown, as with the NIC scenario where no link history is kept, detection latency **cannot** be computed. Say so; do not report 0.

## Why evidence is collected

- Evidence is what you **observed**: command output, a timestamp, the source. A diagnosis is what you **think it means**. Keep them separate, so that a wrong theory doesn't contaminate the record.
- Each hypothesis needs a **discriminating check**: something whose result differs depending on whether the hypothesis is true. "Connection refused" against "timeout" is a classic example.
- Evidence is also what you hand over when escalating. The next engineer should not have to repeat your checks.

## Verification is not the same as applying a repair

- Applying a repair is an action. Verification is a set of checks showing the symptom is gone **and stays gone**: unit active, port listening, HTTP 200, and 2 healthy probes afterwards.
- A plausible but wrong fix (bouncing the NIC for a stopped service) can look like progress. Only verification shows it wasn't.
- MTTR in this lab runs to **verified** recovery, not to when someone typed a command.

## How acceptance decisions are made

- First write down what "correct" means (the expected configuration), then measure.
- **Required** checks gate the decision. **Optional** checks are informational.
- Required FAIL gives **FAIL**. Required evidence missing, unsupported, errored or unreviewed gives **MANUAL REVIEW**, never PASS.
- Results are immutable. A correction leads to a *new* run, and the history shows both runs.

## Why spare reservations must be transactional

- Two technicians can both see "1 available" and reserve it. Without serialization, the check and the write interleave and the part is promised twice.
- Reservation (a hold) and consumption (physical use) are different events. Consumption must be atomic: the ledger, the reservation, the new asset, the failed asset and the incident all change together or not at all.
- Retries happen: a double click, a network timeout. Idempotency keys and a uniqueness constraint make a repeated request harmless.
- A ledger (sum of movements) is auditable. A mutable counter is not.

## What real hardware adds beyond the simulation

- Intermittent and partial faults, such as a flapping link, a marginal optic or correctable memory errors, rather than clean on/off states.
- BMC quirks: missing Redfish properties, stale SEL timestamps, firmware differences between vendors.
- SMART and NVMe health logs, and optics DOM readings (`ethtool -m`): Rx/Tx power and temperature.
- Physical constraints: ESD protection, hot-swap procedures, cable bend radius, airflow, lifting, and keeping hands clear of energized parts.
- Change control, site access rules, and coordination with remote owners.

## When to escalate

| Situation | Escalate to |
|---|---|
| Switch port configuration, VLANs, err-disabled ports | Network engineering |
| Missing feed, PDU or breaker problems, power capacity | Facilities / electrical |
| Crash loops, application errors, possible data corruption | Service owner / on-call engineer |
| Unknown files on data or OS volumes | Data owner / system owner |
| DOA hardware, repeated component failures, RMA | Hardware vendor (through procurement) |
| Unknown processes or suspected compromise | Security |

## Glossary

| Term | Meaning |
|---|---|
| MTTR | Mean time to recovery. Here, detection to **verified** recovery. |
| BMC | Baseboard management controller: the out-of-band management processor on a server. |
| Redfish | DMTF REST API for BMCs (replaces much of IPMI). |
| SEL | System Event Log, the BMC's hardware event log. |
| DOM | Digital optical monitoring: transceiver telemetry (Tx/Rx power, temperature). |
| ENOSPC | errno 28, "No space left on device". |
| PDU | Power distribution unit: rack power strip with outlets on a feed. |
| A/B feeds | Two power paths. They are only redundant if their upstream sources are independent. |
| RMA | Return merchandise authorization: the vendor return process. |
