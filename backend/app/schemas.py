"""Typed request/response schemas (exported through OpenAPI at /api/openapi.json)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

SourceType = Literal["SIMULATED", "LOCAL_LAB", "IMPORTED_SAMPLE"]


class ErrorBody(BaseModel):
    code: str
    message: str
    detail: dict[str, Any] = {}


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class Page(BaseModel):
    items: list[Any]
    total: int
    limit: int
    offset: int


# --------------------------------------------------------------------------- shared refs


class Ref(BaseModel):
    id: int
    display_id: str


class DeviceRef(Ref):
    role: str
    model: str
    health: str
    rack: Optional[str] = None
    position_u: Optional[int] = None


# --------------------------------------------------------------------------- incidents


class IncidentSummary(BaseModel):
    id: int
    display_id: str
    title: str
    severity: str
    status: str
    symptom: str
    device: Optional[DeviceRef]
    scenario_key: Optional[str]
    source_type: SourceType
    source_id: str
    detected_at: datetime
    fault_onset_at: Optional[datetime]
    acknowledged_at: Optional[datetime]
    resolved_at: Optional[datetime]
    assigned_operator: Optional[str]
    next_step: str
    reopen_count: int
    simulation_run: Optional[str]


class TransitionIn(BaseModel):
    action: Literal["acknowledge", "investigate"]
    actor: Optional[str] = None


class EvidenceCollectIn(BaseModel):
    collector: str = Field(..., max_length=48)


class HypothesisIn(BaseModel):
    status: Literal["open", "supported", "refuted"]
    note: str = Field("", max_length=2000)


class RepairIn(BaseModel):
    action_key: str = Field(..., max_length=48)


class ResolveIn(BaseModel):
    root_cause: str = Field("", max_length=4000)


class ReopenIn(BaseModel):
    reason: str = Field(..., min_length=3, max_length=2000)


class NoteIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


class AssignIn(BaseModel):
    operator: str = Field(..., min_length=1, max_length=80)


# --------------------------------------------------------------------------- acceptance


class StorageSpec(BaseModel):
    count: int = Field(..., ge=1, le=64)
    size_gb: int = Field(..., ge=1)
    type: Literal["nvme", "ssd", "hdd"]


class ExpectedConfig(BaseModel):
    cpu_count: int = Field(..., ge=1, le=8)
    cpu_model: str = Field(..., min_length=2, max_length=120)
    memory_gib: int = Field(..., ge=1, le=16384)
    storage: list[StorageSpec]
    nic_count: int = Field(..., ge=1, le=32)
    data_link_speed_mbps: int = Field(..., ge=10)


class IntakeIn(BaseModel):
    asset_tag: str = Field(..., min_length=2, max_length=32)
    serial_number: str = Field(..., min_length=2, max_length=64)
    hostname: str = Field(..., min_length=2, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]*$")
    expected: ExpectedConfig
    intended_rack: Optional[str] = None
    intended_position_u: Optional[int] = Field(None, ge=1, le=60)
    profile_key: str = "nl-compute-standard"
    source_type: SourceType = "SIMULATED"
    use_simulator_model: bool = True


class RunStartIn(BaseModel):
    collector: Literal["simulator", "linux_upload", "redfish_fixture", "redfish_live"] = "simulator"


class CorrectionIn(BaseModel):
    key: str


class ManualReviewIn(BaseModel):
    check_key: str
    decision: Literal["accept", "reject"]
    note: str = Field(..., min_length=3, max_length=2000)


class HandoffIn(BaseModel):
    checklist: dict[str, bool]


class UploadMeta(BaseModel):
    source_type: Literal["LOCAL_LAB", "IMPORTED_SAMPLE"]


# --------------------------------------------------------------------------- inventory & topology


class ReserveIn(BaseModel):
    stock_id: int
    quantity: int = Field(1, ge=1, le=100)
    device_id: Optional[int] = None
    incident_id: Optional[int] = None
    reason: str = Field("", max_length=2000)
    compatibility_exception: bool = False
    exception_reviewed_by: str = Field("", max_length=80)
    exception_note: str = Field("", max_length=2000)


class ConsumeIn(BaseModel):
    replacement_serial: str = Field(..., min_length=3, max_length=64)
    power_input_id: Optional[int] = None
    failed_asset_id: Optional[int] = None
    note: str = Field("", max_length=2000)


class ReleaseIn(BaseModel):
    note: str = Field("", max_length=2000)


class ReceiveIn(BaseModel):
    quantity: int = Field(..., ge=1, le=1000)
    note: str = Field("", max_length=2000)


class AssetTransitionIn(BaseModel):
    to: str
    location: Optional[str] = Field(None, max_length=120)
    device_id: Optional[int] = None
    note: str = Field("", max_length=2000)


class ReturnIn(BaseModel):
    failed_asset_id: int
    failure_summary: str = Field(..., min_length=3, max_length=4000)
    incident_id: Optional[int] = None
    failure_evidence_id: Optional[int] = None
    replacement_asset_id: Optional[int] = None
    original_device_id: Optional[int] = None
    warranty_status: Optional[Literal["known_active", "known_expired", "unknown"]] = None


class ReturnUpdateIn(BaseModel):
    shipping_status: Optional[Literal["awaiting_reference", "ready_to_ship", "shipped", "received_by_vendor", "closed"]] = None
    return_reference: Optional[str] = Field(None, max_length=64)
    warranty_status: Optional[Literal["known_active", "known_expired", "unknown"]] = None


class PlaceIn(BaseModel):
    rack: str
    position_u: int = Field(..., ge=1, le=60)


class CableIn(BaseModel):
    label: Optional[str] = Field(None, max_length=40, pattern=r"^[A-Z0-9][A-Z0-9-]*$")
    cable_type: str = Field(..., max_length=24)
    a_interface_id: int
    b_interface_id: int
    intended_speed_mbps: Optional[int] = None
    length_m: Optional[float] = Field(None, gt=0, le=300)


class CableLabelIn(BaseModel):
    label: str = Field(..., min_length=3, max_length=40, pattern=r"^[A-Z0-9][A-Z0-9-]*$")


# --------------------------------------------------------------------------- portfolio & settings


class ProfileIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    headline: str = Field("", max_length=200)
    summary: str = Field("", max_length=4000)
    links: list[dict[str, str]] = []
    operator_name: str = Field("operator", min_length=1, max_length=80)


class ProjectNoteIn(BaseModel):
    candidate_contribution: str = Field("", max_length=8000)
    lessons_learned: str = Field("", max_length=8000)


class DemoStartIn(BaseModel):
    pass


class LiveLabToggleIn(BaseModel):
    enabled: bool


class AlertmanagerAlert(BaseModel):
    model_config = ConfigDict(extra="allow")
    status: Literal["firing", "resolved"]
    labels: dict[str, str]
    annotations: dict[str, str] = {}
    startsAt: Optional[str] = None
    endsAt: Optional[str] = None
    fingerprint: Optional[str] = None


class AlertmanagerWebhook(BaseModel):
    model_config = ConfigDict(extra="allow")
    version: str = "4"
    status: Literal["firing", "resolved"]
    alerts: list[AlertmanagerAlert] = Field(..., max_length=100)
