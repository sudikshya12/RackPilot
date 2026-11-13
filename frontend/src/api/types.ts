export type SourceType = "SIMULATED" | "LOCAL_LAB" | "IMPORTED_SAMPLE";
export type Severity = "critical" | "major" | "minor";
export type IncidentStatus = "detected" | "acknowledged" | "investigating" | "repair_applied" | "verification" | "resolved";
export type CheckResult = "PASS" | "FAIL" | "MANUAL_REVIEW" | "UNSUPPORTED" | "SKIPPED" | "ERROR";

export interface DeviceRef { id: number; display_id: string; role: string; model: string; health: string; rack: string | null; position_u: number | null }

export interface DeviceCard extends DeviceRef {
  hostname: string; u_height: number; face: string; manufacturer: string; health_source: SourceType; health_updated_at: string | null;
  asset_id: number | null; asset: string | null; serial: string | null; origin: string; acceptance: string | null;
  open_incidents: { id: number; display_id: string; severity: Severity; status: IncidentStatus; source_type: SourceType }[];
  power_findings: PowerFinding[];
}
export interface PowerFinding { code: string; severity: string; message: string; device?: string; device_id?: number }

export interface Rack {
  id: number; display_id: string; name: string; row: string; u_height: number; site: string; free_units: number; basis: string;
  devices: DeviceCard[]; planned: { intake_id: number; intake: string; hostname: string; position_u: number; u_height: number; status: string }[];
}

export interface IncidentSummary {
  id: number; display_id: string; title: string; severity: Severity; status: IncidentStatus; symptom: string; device: DeviceRef | null;
  scenario_key: string | null; source_type: SourceType; source_id: string; detected_at: string; fault_onset_at: string | null;
  acknowledged_at: string | null; resolved_at: string | null; assigned_operator: string | null; next_step: string; reopen_count: number;
  simulation_run: string | null; simulation_status: string | null; demo_key: string | null; origin: string;
}
export interface Evidence {
  id: number; display_id: string; collector: string; command: string; output: string; observations: Record<string, unknown>;
  interpretation: string; limitations: string; source_type: SourceType; source_id: string; collected_at: string;
}
export interface VerificationCheck { key: string; name: string; passed: boolean; observed: string; expected: string }
export interface IncidentDetail extends IncidentSummary {
  detection_rule: string; runbook_slug: string | null; root_cause: string; repair_applied_at: string | null; verified_at: string | null;
  events: { id: number; kind: string; occurred_at: string; actor: string; summary: string; from_status: string | null; to_status: string | null; detail: Record<string, unknown> }[];
  hypotheses: { id: number; key: string; statement: string; discriminating_check: string; status: "open" | "supported" | "refuted"; note: string }[];
  repairs: { id: number; action_key: string; description: string; applied_at: string; actor: string; source_type: SourceType }[];
  verifications: { id: number; executed_at: string; passed: boolean; checks: VerificationCheck[]; after_repair_id: number | null; source_type: SourceType; source_id: string }[];
  evidence: Evidence[];
  collectors: { key: string; label: string; group: string; recommended: boolean }[];
  repair_options: { key: string; label: string; description: string; tests_hypothesis: string | null; requires_spare_workflow: boolean }[];
  metrics: IncidentMetrics;
  simulation: { display_id: string; status: string; phase: string; probe_count: number; healthy_since_repair: number; demo_key: string | null } | null;
  allowed_transitions: string[];
}
export interface IncidentMetrics { detection_latency_s: number | null; detection_latency_note: string | null; acknowledgment_latency_s: number | null; repair_interval_s: number | null }
export interface Stats { count: number; median: number | null; mean: number | null }
export interface AggregateMetrics {
  definitions: Record<string, string>;
  by_source: Record<SourceType, { incidents: number; detection_latency_s: Stats; acknowledgment_latency_s: Stats; mttr_s: Stats; excluded_unknown_onset: number;
    drills: ({ incident: string; id: number; scenario: string | null; status: string; detected_at: string } & IncidentMetrics)[] }>;
}

export interface RunSummary {
  id: number; display_id: string; intake_id: number; intake: string; hostname: string; run_number: number; status: string;
  disposition: "PASS" | "FAIL" | "MANUAL_REVIEW" | null; effective_disposition: string | null; created_at: string; started_at: string | null;
  completed_at: string | null; operator: string; collector: string; source_type: SourceType; source_id: string; counts: Record<string, number>;
  checks_total: number; checks_done: number; origin: string;
}
export interface CheckResultRow {
  id: number; check_key: string; check_name: string; check_version: string; required: boolean; result: CheckResult; expected_value: string | null;
  observed_value: string | null; unit: string | null; detail: string; executed_at: string; duration_ms: number | null; source_type: SourceType; evidence: Evidence | null;
}
export interface RunDetail extends RunSummary {
  expected_snapshot: Record<string, unknown>; profile_snapshot: { key: string; name: string; version: string; checks: { check_key: string; required: boolean }[] };
  observed_snapshot: Record<string, unknown>; corrections_before_run: Correction[]; manual_reviews: Record<string, { decision: string; note: string; by: string; at: string }>;
  follow_up_actions: string[]; results: CheckResultRow[];
}
export interface Correction { key: string; label: string; physical_action: string; applied_at?: string; actor?: string; source_type?: SourceType; applied?: boolean; check?: string }
export interface Expected { cpu_count: number; cpu_model: string; memory_gib: number; storage: { count: number; size_gb: number; type: string }[]; nic_count: number; data_link_speed_mbps: number }
export interface Intake {
  id: number; display_id: string; asset_tag: string; serial_number: string; hostname: string; expected: Expected; intended_rack: string | null;
  intended_position_u: number | null; profile: { key: string; name: string; version: string; checks: { check_key: string; required: boolean }[] };
  source_type: SourceType; status: string; operator: string; created_at: string; has_simulator_model: boolean; simulated_corrections: Correction[];
  has_upload: boolean; uploaded_source_type: SourceType | null; available_corrections: Correction[]; runs: RunSummary[]; origin: string;
  handoff_checklist: Record<string, string>;
}

export interface Asset {
  id: number; display_id: string; serial_number: string; asset_type: string; manufacturer: string; model: string; status: string; location: string;
  installed_in: DeviceRef | null; warranty_status: string; warranty_end: string | null; part_number: string | null; notes: string; origin: string; simulation_run_id: number | null;
}
export interface AuditEvent {
  id: number; occurred_at: string; actor: string; action: string; entity_type: string; entity_id: number; entity_display: string; summary: string;
  before: Record<string, unknown> | null; after: Record<string, unknown> | null; related: { type: string; id: number; display: string }[]; origin: string; simulation_run_id: number | null;
}
export interface Stock {
  id: number; display_id: string; part_type_id: number; part_number: string; part_name: string; category: string; location: string;
  on_hand: number; reserved: number; available: number; reorder_threshold: number; low_stock: boolean; compatible_models: string[]; compatible?: boolean;
}
export interface Reservation {
  id: number; display_id: string; stock_id: number; stock: string; part_number: string; part_name: string; quantity: number; status: string;
  device: DeviceRef | null; incident_id: number | null; reason: string; compatibility_exception: boolean; exception_reviewed_by: string; exception_note: string;
  actor: string; created_at: string; consumed_at: string | null; released_at: string | null; origin: string;
}
export interface Txn { id: number; display_id: string; occurred_at: string; stock: string; part_number: string; kind: string; quantity_delta: number; reservation_id: number | null; asset_id: number | null; note: string; actor: string; origin: string }
export interface ReturnRecord {
  id: number; display_id: string; failed_asset: Asset; replacement_asset: Asset | null; original_device: DeviceRef | null; incident_id: number | null;
  failure_evidence_id: number | null; failure_summary: string; warranty_status: string; return_reference: string | null; shipping_status: string;
  actor: string; created_at: string; updated_at: string; origin: string;
}
export interface CableEnd { interface_id: number; interface: string; device_id: number; device: string; connector: string; kind: string; rack: string | null }
export interface Cable { id: number; label: string | null; cable_type: string; a: CableEnd; b: CableEnd; intended_speed_mbps: number | null; length_m: number | null; status: string; notes: string; origin: string }
export interface TraceHop { type: "endpoint" | "cable" | "pass_through"; device?: string; interface?: string; label?: string | null; cable_type?: string; status?: string; connector?: string; role?: string; from?: string; to?: string; intended_speed_mbps?: number | null; length_m?: number | null; interface_id?: number; device_id?: number; cable_id?: number }
export interface PowerInputView { input: string; input_id: number; connector: string; outlet: string | null; pdu: string | null; feed: string | null; upstream: string | null; rated_w: number | null; estimated_load_w: number | null; component_asset: string | null; component_asset_id: number | null }
export interface DeviceDetail extends Omit<DeviceCard, "acceptance"> {
  mgmt_address: string; notes: string;
  interfaces: { id: number; name: string; kind: string; connector: string; speed_capability_mbps: number | null; mac: string; description: string; pass_through_id: number | null }[];
  cables: Cable[]; power: { inputs: PowerInputView[]; findings: PowerFinding[]; independence: string; disclaimer: string };
  incidents: IncidentSummary[]; acceptance: Intake[]; asset_detail: Asset | null; components: Asset[]; audit: AuditEvent[];
}
export interface DemoStep { key: string; title: string; body: string; done: boolean; auto?: boolean; view?: boolean; optional?: boolean; route?: string | null }
export interface DemoStatus {
  key: string; title: string; project: string; scenario: string | null; minutes: string; summary: string;
  run: { display_id: string; status: string; phase: string; probe_count: number; started_at: string; incident_id: number | null; healthy_since_repair: number | null } | null;
  steps: DemoStep[]; current: number | null; complete: boolean;
}
