# Data Dictionary

Source of truth: `backend/app/models.py`. Migration: `backend/alembic/versions/*_initial_schema.py`.

Conventions that apply to every table:

- `id` is an internal integer primary key. `display_id` is the human-readable identifier and is unique.
- Timestamps are stored as UTC (`UTCDateTime` rejects naive datetimes) and returned as ISO-8601 with `Z`.
- `origin ∈ {seed, simulation, operator, imported, local_lab}`, enforced by CHECK constraints.
- `source_type ∈ {SIMULATED, LOCAL_LAB, IMPORTED_SAMPLE}`, enforced by CHECK constraints.
- `simulation_run_id` is an FK to `simulation_runs` with `ON DELETE CASCADE`. Deleting a run removes everything it owns.
- Foreign keys are enforced (`PRAGMA foreign_keys=ON`).

## Topology

| Table | Purpose | Key columns and units | Constraints and indexes |
|---|---|---|---|
| `sites` | Facility (North Lab, `SITE-NL`). | `name`, `description` | `display_id` unique |
| `racks` | Rack in a site. | `site_id`, `row`, `u_height` (rack units) | `u_height` 1–60 |
| `devices` | Server, switch, patch panel or PDU. | `role`, `model`, `rack_id`, `position_u` (lowest U), `u_height` (U, 0 = zero-U PDU), `face`, `mgmt_address`, `asset_id`, `health` (`healthy`/`degraded`/`critical`/`unknown`), `health_source`, `health_updated_at` | role CHECK; `u_height` 0–10; `position_u ≥ 1`; `asset_id` unique; index (`rack_id`, `position_u`). Overlap and bounds are validated in `services/topology.py` (`assert_space_free`). |
| `device_interfaces` | Network port or patch-panel port. | `kind` (`data`/`mgmt`/`patch_front`/`patch_rear`/`uplink`), `connector_type` (RJ45, SFP+, LC, QSFP28), `speed_capability_mbps` (Mb/s), `mac_address`, `pass_through_id` (front↔rear pairing on patch panels) | unique (`device_id`, `name`) |
| `power_feeds` | Upstream circuit. | `upstream_source` (NULL = unknown), `voltage_v` (V), `capacity_w` (W, modeled) | `display_id` unique |
| `pdu_outlets` | PDU outlet and the feed it is on. | `pdu_device_id`, `name`, `feed_id`, `connector_type` | unique (`pdu_device_id`, `name`) |
| `power_inputs` | Device PSU inlet. | `name` (PSU1/PSU2), `outlet_id` (NULL = not connected), `rated_w` (W), `estimated_load_w` (W, **estimate**), `component_asset_id` (installed PSU asset) | unique (`device_id`, `name`); `outlet_id` unique (one inlet per outlet) |
| `cable_connections` | Explicit cable between two interfaces. | `label` (NULL = unlabeled defect), `cable_type`, `a_interface_id`, `b_interface_id`, `intended_speed_mbps` (Mb/s), `length_m` (m), `status` | `label` unique; `a_interface_id` unique; `b_interface_id` unique; CHECK a ≠ b; status CHECK. Cross-column endpoint reuse and connector compatibility are validated in `topology.validate_cable`. |

## Assets and inventory

| Table | Purpose | Key columns and units | Constraints and indexes |
|---|---|---|---|
| `assets` | Trackable physical item (chassis, PSU, …). | `display_id` (asset tag), `serial_number`, `asset_type`, `part_type_id`, `status`, `location`, `installed_in_device_id`, `warranty_status` (`known_active`/`known_expired`/`unknown`), `warranty_end` | `serial_number` unique; status CHECK (9 lifecycle states); index on `status`. Allowed transitions are in `inventory.LIFECYCLE`. |
| `part_types` | Orderable part definition. | `part_number`, `category` (psu/dimm/transceiver/disk), `connector_or_form` | `part_number` unique |
| `part_compatibility` | Part type ↔ device model compatibility list. | `part_type_id`, `device_model` | unique (`part_type_id`, `device_model`) |
| `spare_stock` | Stock location for a part type. **No quantity column.** | `location`, `reorder_threshold` | unique (`part_type_id`, `location`); threshold ≥ 0 |
| `inventory_transactions` | Immutable ledger. On hand = `SUM(quantity_delta)` per stock row. | `kind` (`receive`/`consume`/`adjust`/`return_out`/`return_in`), `quantity_delta` (units), `reservation_id`, `asset_id`, `occurred_at` | delta ≠ 0; unique (`reservation_id`, `kind`) blocks double consumption at the DB level; index on `occurred_at`, `stock_id` |
| `reservations` | Hold on stock. Separate from consumption. | `quantity` (units), `status` (`active`/`consumed`/`released`), `device_id`, `incident_id`, `compatibility_exception`, `exception_reviewed_by`, `exception_note`, `consumed_at`, `released_at` | quantity > 0; status CHECK; index (`stock_id`, `status`) |
| `return_records` | RMA record. The return is recorded only; no vendor is contacted. | `failed_asset_id`, `original_device_id`, `incident_id`, `failure_evidence_id`, `failure_summary`, `warranty_status`, `return_reference`, `shipping_status`, `replacement_asset_id` | `failed_asset_id` unique (one open return per asset); shipping-status CHECK |

## Incidents

| Table | Purpose | Key columns | Constraints and indexes |
|---|---|---|---|
| `incidents` | Detected problem. | `severity`, `status` (6 lifecycle states), `device_id`, `scenario_key`, `runbook_slug`, `detection_rule`, `source_type`, `source_id`, `fault_onset_at` (NULL = unknown), `detected_at`, `acknowledged_at`, `repair_applied_at`, `verified_at`, `resolved_at`, `assigned_operator`, `reopen_count`, `root_cause` | severity/status/source CHECKs; index (`status`, `severity`) |
| `incident_events` | Append-only timeline. | `kind`, `occurred_at`, `from_status`, `to_status`, `actor`, `summary`, `detail` (JSON) | index on `incident_id` |
| `hypotheses` | Candidate diagnosis with a discriminating check. | `key`, `statement`, `discriminating_check`, `status` (`open`/`supported`/`refuted`), `note` | unique (`incident_id`, `key`) |
| `repair_actions` | Recorded corrective action. | `action_key`, `description`, `applied_at`, `actor`, `source_type` | |
| `verifications` | Result of a verification execution. | `executed_at`, `after_repair_id`, `passed`, `checks` (JSON list of {key, name, passed, observed, expected}), `source_type`, `source_id` | |
| `evidence_items` | Collected evidence (incident or acceptance). | `collector`, `command` (display only), `output`, `observations` (JSON), `interpretation`, `limitations`, `source_type`, `source_id`, `collected_at` | indexes on `incident_id`, `acceptance_run_id`, `device_id` |
| `runbooks` | Operational procedures. | `slug`, `title`, `symptom`, `scenario_keys`, `sections` (JSON), `version` | `slug` unique |

## Acceptance

| Table | Purpose | Key columns | Constraints and indexes |
|---|---|---|---|
| `acceptance_profiles` | Named set of checks and whether each is required. | `key`, `version`, `checks` (JSON: [{check_key, required}]) | `key` unique |
| `intake_records` | A server's expected configuration at intake. | `asset_tag`, `serial_number`, `hostname`, `expected` (JSON: cpu_count, cpu_model, memory_gib (GiB), storage[], nic_count, data_link_speed_mbps (Mb/s)), `intended_rack_id`, `intended_position_u`, `profile_id`, `status`, `simulated_hardware` (simulator model), `simulated_corrections` (labeled list), `uploaded_observations`, `uploaded_source_type` | status CHECK |
| `acceptance_runs` | One execution. Immutable once completed. | `run_number`, `status`, `disposition` (`PASS`/`FAIL`/`MANUAL_REVIEW`), `collector`, `source_type`, `source_id`, `expected_snapshot`, `profile_snapshot`, `observed_snapshot`, `corrections_before_run`, `manual_reviews` (separate annotations), `follow_up_actions`, timestamps | unique (`intake_id`, `run_number`) |
| `acceptance_check_results` | Per-check outcome. | `check_key`, `check_version`, `required`, `result` (6 values), `expected_value`, `observed_value`, `unit`, `detail`, `evidence_item_id`, `executed_at`, `duration_ms` (ms), `source_type` | unique (`run_id`, `check_key`); result CHECK |

## Platform

| Table | Purpose | Key columns | Constraints and indexes |
|---|---|---|---|
| `audit_events` | Audit history of material changes. | `occurred_at`, `actor`, `action`, `entity_type`, `entity_id`, `entity_display`, `summary`, `before`, `after`, `related`, `origin`, `simulation_run_id` | index (`entity_type`, `entity_id`); index on `occurred_at` |
| `simulation_runs` | Deterministic scenario or demo state. | `scenario_key`, `demo_key`, `status`, `phase`, `probe_count`, `state` (JSON), `started_at`, `next_tick_at`, `paused_at`, `completed_at`, `device_id`, `incident_id` (soft link) | status CHECK |
| `metric_observations` | Time series sample. | `metric`, `value` (NULL = not collected), `unit` (e.g. `bool`, `ms`, `percent`, `GiB`, `W`, `packets/s`), `labels`, `observed_at`, `source_type`, `source_id` | index (`device_id`, `metric`, `observed_at`) |
| `stream_events` | Persisted SSE events for replay. | `id` (event ID), `topic`, `payload`, `created_at` | |
| `idempotency_keys` | Stored first response per key and endpoint. | `key`, `endpoint`, `request_hash` (SHA-256), `response`, `status_code` | unique (`key`, `endpoint`) |
| `candidate_profile` | Editable portfolio identity. | `name` (default `[Candidate Name]`), `headline`, `summary`, `links`, `operator_name` (actor recorded on actions) | |
| `project_notes` | Candidate-written contribution and lessons per case study. | `slug`, `candidate_contribution`, `lessons_learned` | `slug` unique |
| `lab_settings` | Key/value runtime settings. | `livelab_enabled`, `livelab_state` | |
| `display_counters` | Monotonic counters for display IDs (`INC-0001`, `RSV-0001`, `TXN-00001`, …). | `prefix`, `value` | |
