# Case Study 3: Rack, Cabling & Asset Lifecycle

*RackOps Lab, an independent interview lab by [Candidate Name]. Topology is a modeled lab, not a discovered one.*

## 1. Problem

Physical records drift. Cables go unlabeled, "redundant" power turns out to share one UPS, spares get consumed twice or not at all, and failed parts disappear without a return record. A repair is only finished when the inventory, the asset history and the return queue agree with what happened.

## 2. Relevance to data center operations

Technicians install, cable, label and replace hardware every day. Accurate rack elevations, traceable cabling, power-path awareness and disciplined spares handling prevent outages caused by mistakes and keep RMA logistics auditable.

## 3. Implemented workflow

- **Rack elevation.** Two 42U racks, front and rear views, U numbering, free space, health LEDs, incident markers, planned intake positions, and a text-table equivalent. The server rejects overlapping and out-of-bounds placements.
- **Cable explorer.**
  - Explicit endpoints, including patch-panel front and rear ports with modeled pass-through.
  - Visual and text path trace that follows only modeled links.
  - Validation for occupied endpoints, missing endpoints, incompatible connectors and missing labels.
  - Copyable paths and printable QR labels that link to local routes.
- **Power topology.** Device inputs map to PDU outlets, outlets to feeds, and feeds to upstream sources. Findings flag shared upstream sources (even when the PDU names differ), missing connections, and unknown upstream. Loads are labeled as estimates.
- **Asset lifecycle.** Received → Stored → Installed → Active, plus Quarantined, In repair, Pending return, Returned and Decommissioned. Transitions are validated, required information is enforced, and every change is audited.
- **Spares.**
  - Stock is ledger-derived.
  - Reservation and consumption are separate steps.
  - Negative stock, over-reservation and double consumption are blocked (idempotency keys, plus a DB uniqueness constraint on reservation and kind).
  - Incompatible parts need a reviewed exception with a named reviewer and a justification.
- **Returns / RMA.** Records the failed asset, the original device, the incident, the evidence, warranty status (known or unknown), the return reference and the shipping state. No vendor is contacted.

## 4. Architecture

`services/topology.py` (placement, cable validation, trace, power analysis) · `services/inventory.py` (lifecycle, ledger, reserve, consume, returns) · `BEGIN IMMEDIATE` write sessions (`db.py`). UI: `components/rack/RackElevation.tsx`, `CableTrace.tsx`, `DevicePanel.tsx`, `pages/Infrastructure.tsx`, `pages/Spares.tsx`, `pages/Returns.tsx`, `pages/AssetDetail.tsx`.

## 5. Demonstration

Guided demo **Replace a failed component and reconcile inventory**:

1. The PSU2 fault on lab-srv-04 is detected.
2. Open the device.
3. Review the evidence: Redfish Power, SEL and PDU outlet. Feed loss is refuted.
4. Find a compatible spare (NL-PSU-800P). NL-PSU-550S is flagged incompatible.
5. Reserve the spare.
6. Consume it with serial `SIM-PSU-SP-0103`.
7. Move the failed PSU to the return queue.
8. Re-run the health check.
9. Resolve, then review the device's audit trail.

The workflow completion is real; the physical swap is simulated.

## 6. Collected results

Produced by running the application. The seeded documentation defects are detected by the validators:

| Defect | Where |
|---|---|
| Unlabeled DAC cable | lab-srv-03 eth1 ↔ lab-sw-01 Eth1/3 |
| Copper cable recorded on an SFP+ port | CBL-0199 |
| Missing power connection | lab-srv-03 PSU2 |
| Shared upstream (both feeds trace to UPS-A) | lab-srv-05 |
| Unknown upstream | lab-sw-02 PSU2 (temporary strip) |

See **Racks & cabling** and the case-study page. Stock movements are listed in the inventory ledger.

## 7. Limitations

- The topology is a hand-modeled documentation set. No LLDP, SNMP or NetBox discovery is performed (NetBox is a read-only JSON import).
- The power analysis is a documentation check, not an electrical design certification. Loads are estimates.
- QR codes encode local routes, which work only where the app is reachable.

## 8. Candidate contribution

[To be written by the candidate]

## 9. Lessons learned

[To be written by the candidate]

## 10. Reproduction

```bash
cd backend && uv sync && uv run alembic upgrade head && uv run python -m app.seed
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
cd ../frontend && npm ci && npm run dev    # http://127.0.0.1:5173/infrastructure
cd ../backend && uv run pytest tests/test_inventory_topology.py
```
