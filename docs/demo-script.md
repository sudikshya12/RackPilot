# 5-Minute Interview Demonstration Script

**Before the interview**

1. Start the backend and the frontend (see README).
2. Open `http://127.0.0.1:5173/`.
3. On **/demo**, press *Reset all simulation data* so every demo starts clean.
4. Keep the browser at about 1440 px wide.

**Controls.** The bottom dock has Next step (Shift+N), View, Pause, Restart and Exit. Every "Next step" calls the same backend workflow as the normal buttons. Steps marked *Auto* complete on their own as the simulator probes.

---

## 0:00 – 0:30 · Portfolio overview (`/`)

**Say:** "This is RackOps Lab, an independent lab I built for this interview. It covers three things a technician does every shift: restore failed services with evidence, reject hardware that doesn't match its build sheet, and keep rack, cabling and spare-part records reconciled."

**Point at:**

- The **Operations Overview** dashboard: four metrics, the rack, **Needs attention** and **Recent activity**. "Each metric is computed from stored records and links to the filtered list behind it."
- The **Simulation mode** indicator in the header (click it): what is simulated, which local-lab sources are connected, and where to configure them. "Nothing is mixed across sources, and missing data shows as Unknown, never as zero."
- If asked about the project itself: **About & Documentation** in the sidebar.

## 0:30 – 1:50 · Demo 1: Restore a failed service

1. Open **Demonstrations**, start **Restore a failed service**, then return to **Overview**. The compact control bar appears at the bottom. **Say:** "Healthy baseline: the probe hits /health every 3 seconds."
2. *Auto* steps. lab-srv-02 turns red in the rack and INC appears in the queue, pushed live over SSE. **Say:** "The detection rule needs 2 consecutive failures, so detection latency is exactly 3 seconds, and the onset is known because the simulator injected it."
3. **Next step:** acknowledge. **Next step:** evidence. Open `systemctl_status` in the Evidence panel. **Point at** the output, the *Observed* interpretation, the source badge and the timestamp. "Observation is kept separate from diagnosis, which lives in Hypotheses."
4. **Next step:** the wrong hypothesis. **Point at** the Verification panel showing FAILED and the status back at *Investigating*. "I bounced eth1 to test the network-path theory. Verification failed, so the incident cannot be resolved."
5. **Next step:** start the unit. Run verification immediately. **Point at** *waiting for 2 healthy probes*. "Pressing a button doesn't prove recovery. The checks do."
6. **Next step:** verification passes. Resolve and open **Summary**: timeline, evidence, repairs, metrics, all generated from stored records.

## 1:50 – 3:10 · Demo 2: Reject and re-test a misconfigured server

1. On `/demo`, start **Reject and re-test**. The intake INT-0001 opens. **Point at** the expected configuration: 128 GiB, 10 Gb/s.
2. **Next step:** run #1. Checks fill in live. The result is **FAIL**: memory 64 GiB, link 1000 Mb/s. **Say:** "A required failure is a FAIL. Missing required evidence would be MANUAL REVIEW, never PASS. Optional checks are visible but don't decide."
3. **Next step:** record two corrections. **Point at** the `SIMULATED` label and the physical-action text.
4. **Next step:** run #2 is **PASS**. Click **Compare first and latest**. **Point at** only two rows changed, and the corrections listed between the runs. "Run #1 is immutable; the re-test is a new record."
5. Open **Report**: printable HTML and JSON, rendered from the persisted run.

## 3:10 – 4:30 · Demo 3: Replace a failed component

1. Start **Replace a failed component**. PSU2 on lab-srv-04 is detected (Redfish fixture). Open the device drawer. **Point at** the Power tab: inputs, outlets, feeds.
2. **Next step** ×2: acknowledge, then evidence. **Say:** "The outlet is ON and other FEED-B loads draw current, so it's the PSU, not the feed."
3. On the Spares page, **point at** NL-PSU-800P *Compatible* and NL-PSU-550S *Not compatible*. **Reserve**. **Point at** *Available* dropping while *On hand* stays the same.
4. **Consume**, with serial `SIM-PSU-SP-0103` prefilled. **Say:** "One transaction: ledger −1, reservation consumed, new asset installed, failed unit quarantined, repair recorded on the incident. Repeating it with the same idempotency key cannot consume twice."
5. **Create return record**. Then **Next step**: the health re-check passes. **Next step**: resolve. Open the device **Audit** tab, which shows the full trail from detection to RMA.

## 4:30 – 5:00 · Close

**Say:** "Every workflow is backed by tests: 40 backend tests plus Playwright journeys. The limitations are documented. The evidence is simulated or modeled unless it's labeled Local lab. Real hardware would add BMC quirks, intermittent faults and physical safety, which I'd escalate per the runbooks."

---

## Likely questions

| Question | Answer |
|---|---|
| How is detection latency measured? | Detected timestamp minus known fault onset. When onset is unknown (the NIC scenario), it is reported as unavailable, never as 0. |
| Why two consecutive failures? | To avoid paging on a single dropped probe. The cost is one interval of extra latency. |
| Could someone resolve without fixing it? | No. `resolve()` requires a passing verification executed after the latest repair. A wrong repair fails verification and moves the incident back to investigating. |
| What if two people reserve the last spare at once? | Write sessions start with `BEGIN IMMEDIATE`, so the availability check and the insert are serialized. The second request gets `insufficient_stock`. |
| What stops double consumption? | The reservation status check, idempotency keys, and a DB unique constraint on (reservation_id, kind) in the ledger. |
| Is the rack data real? | No. It is a modeled lab topology, labeled as such. NetBox import and the Redfish adapter show how real sources would plug in, both read-only. |
| What about real hardware? | Upload `rackops_collect.py` output (labeled Local lab), point the Redfish adapter at a BMC, or enable the live lab, which is a real local process outage. |
| What would you escalate? | Switch configuration to network, feeds to facilities, crash loops to the service owner, repeated PSU failures to the vendor. |
