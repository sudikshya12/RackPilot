"""Shared data model for RackOps Lab.

Conventions
-----------
* ``id`` is a stable internal integer key; ``display_id`` is the human-readable identifier.
* All timestamps are timezone-aware UTC (stored as ISO text by SQLite via ``UTCDateTime``).
* ``origin`` records who owns a row: seed | simulation | operator | imported | local_lab.
  Demo reset only removes ``simulation`` rows (and restores seed baselines).
* Measurements and evidence carry provenance: ``source_type`` (SIMULATED | LOCAL_LAB |
  IMPORTED_SAMPLE), ``source_id``, ``collected_at``/``observed_at`` and ``simulation_run_id``.
* Every measurement has an explicit ``unit``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Always store and return timezone-aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetimes are not allowed; use UTC-aware datetimes")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


SOURCE_TYPES = ("SIMULATED", "LOCAL_LAB", "IMPORTED_SAMPLE")
ORIGINS = ("seed", "simulation", "operator", "imported", "local_lab")
_src_check = "source_type IN ('SIMULATED','LOCAL_LAB','IMPORTED_SAMPLE')"
_origin_check = "origin IN ('seed','simulation','operator','imported','local_lab')"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)


# --------------------------------------------------------------------------- topology


class Site(TimestampMixin, Base):
    __tablename__ = "sites"
    __table_args__ = (CheckConstraint(_origin_check, name="ck_sites_origin"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    display_id: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(16), default="seed")
    racks: Mapped[list[Rack]] = relationship(back_populates="site", order_by="Rack.display_id")


class Rack(TimestampMixin, Base):
    __tablename__ = "racks"
    __table_args__ = (
        CheckConstraint("u_height BETWEEN 1 AND 60", name="ck_racks_u_height"),
        CheckConstraint(_origin_check, name="ck_racks_origin"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    display_id: Mapped[str] = mapped_column(String(32), unique=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    row: Mapped[str] = mapped_column(String(32), default="")
    u_height: Mapped[int] = mapped_column(Integer, default=42)
    description: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(16), default="seed")
    site: Mapped[Site] = relationship(back_populates="racks")
    devices: Mapped[list[Device]] = relationship(back_populates="rack")


class Device(TimestampMixin, Base):
    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint("u_height BETWEEN 0 AND 10", name="ck_devices_u_height"),
        CheckConstraint("position_u IS NULL OR position_u >= 1", name="ck_devices_position"),
        CheckConstraint("role IN ('server','switch','patch_panel','pdu')", name="ck_devices_role"),
        CheckConstraint(_origin_check, name="ck_devices_origin"),
        Index("ix_devices_rack_position", "rack_id", "position_u"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    display_id: Mapped[str] = mapped_column(String(64), unique=True)
    hostname: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16))
    manufacturer: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(80), index=True)
    rack_id: Mapped[Optional[int]] = mapped_column(ForeignKey("racks.id", ondelete="SET NULL"), index=True)
    position_u: Mapped[Optional[int]] = mapped_column(Integer)
    u_height: Mapped[int] = mapped_column(Integer, default=1)
    face: Mapped[str] = mapped_column(String(8), default="front")  # front | rear | full(depth)
    mgmt_address: Mapped[str] = mapped_column(String(64), default="")
    asset_id: Mapped[Optional[int]] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"), unique=True)
    # Health as last determined by a check, with provenance. "unknown" until something reports.
    health: Mapped[str] = mapped_column(String(16), default="unknown")
    health_source: Mapped[str] = mapped_column(String(16), default="SIMULATED")
    health_updated_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    notes: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(16), default="seed")

    rack: Mapped[Optional[Rack]] = relationship(back_populates="devices")
    asset: Mapped[Optional[Asset]] = relationship(foreign_keys=[asset_id])
    interfaces: Mapped[list[DeviceInterface]] = relationship(back_populates="device", order_by="DeviceInterface.id")
    power_inputs: Mapped[list[PowerInput]] = relationship(back_populates="device", order_by="PowerInput.name", foreign_keys="PowerInput.device_id")


class DeviceInterface(TimestampMixin, Base):
    __tablename__ = "device_interfaces"
    __table_args__ = (
        UniqueConstraint("device_id", "name", name="uq_iface_device_name"),
        CheckConstraint("kind IN ('data','mgmt','patch_front','patch_rear','uplink')", name="ck_iface_kind"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(16), default="data")
    connector_type: Mapped[str] = mapped_column(String(16))  # RJ45 | SFP+ | LC | QSFP28
    speed_capability_mbps: Mapped[Optional[int]] = mapped_column(Integer)
    mac_address: Mapped[str] = mapped_column(String(32), default="")
    # Patch panel pass-through: front port <-> rear port, explicitly modeled.
    pass_through_id: Mapped[Optional[int]] = mapped_column(ForeignKey("device_interfaces.id", ondelete="SET NULL"))
    description: Mapped[str] = mapped_column(String(200), default="")
    device: Mapped[Device] = relationship(back_populates="interfaces")


class PowerFeed(TimestampMixin, Base):
    __tablename__ = "power_feeds"
    __table_args__ = (CheckConstraint(_origin_check, name="ck_feeds_origin"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    display_id: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    # Upstream source identity, e.g. "UPS-A (modeled)". NULL means unknown upstream.
    upstream_source: Mapped[Optional[str]] = mapped_column(String(120))
    voltage_v: Mapped[Optional[float]] = mapped_column(Float)
    capacity_w: Mapped[Optional[float]] = mapped_column(Float)  # modeled capacity
    origin: Mapped[str] = mapped_column(String(16), default="seed")


class PduOutlet(TimestampMixin, Base):
    __tablename__ = "pdu_outlets"
    __table_args__ = (UniqueConstraint("pdu_device_id", "name", name="uq_outlet_pdu_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    pdu_device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(32))
    feed_id: Mapped[Optional[int]] = mapped_column(ForeignKey("power_feeds.id", ondelete="SET NULL"), index=True)
    connector_type: Mapped[str] = mapped_column(String(16), default="C13")
    pdu: Mapped[Device] = relationship(foreign_keys=[pdu_device_id])
    feed: Mapped[Optional[PowerFeed]] = relationship()


class PowerInput(TimestampMixin, Base):
    __tablename__ = "power_inputs"
    __table_args__ = (UniqueConstraint("device_id", "name", name="uq_power_input_device_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(32))  # PSU1 / PSU2
    connector_type: Mapped[str] = mapped_column(String(16), default="C14")
    outlet_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pdu_outlets.id", ondelete="SET NULL"), unique=True)
    rated_w: Mapped[Optional[float]] = mapped_column(Float)
    estimated_load_w: Mapped[Optional[float]] = mapped_column(Float)  # ESTIMATE, documented as such
    component_asset_id: Mapped[Optional[int]] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
    device: Mapped[Device] = relationship(back_populates="power_inputs", foreign_keys=[device_id])
    outlet: Mapped[Optional[PduOutlet]] = relationship()
    component_asset: Mapped[Optional[Asset]] = relationship(foreign_keys=[component_asset_id])


class CableConnection(TimestampMixin, Base):
    __tablename__ = "cable_connections"
    __table_args__ = (
        UniqueConstraint("a_interface_id", name="uq_cable_a_endpoint"),
        UniqueConstraint("b_interface_id", name="uq_cable_b_endpoint"),
        CheckConstraint("a_interface_id <> b_interface_id", name="ck_cable_distinct_endpoints"),
        CheckConstraint("status IN ('connected','planned','faulty','disconnected')", name="ck_cable_status"),
        CheckConstraint(_origin_check, name="ck_cables_origin"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[Optional[str]] = mapped_column(String(40), unique=True)  # NULL = unlabeled (a defect)
    cable_type: Mapped[str] = mapped_column(String(24))  # cat6a | om4-lc-lc | dac-sfp+
    a_interface_id: Mapped[int] = mapped_column(ForeignKey("device_interfaces.id", ondelete="RESTRICT"))
    b_interface_id: Mapped[int] = mapped_column(ForeignKey("device_interfaces.id", ondelete="RESTRICT"))
    intended_speed_mbps: Mapped[Optional[int]] = mapped_column(Integer)
    length_m: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="connected")
    notes: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(16), default="seed")
    a_interface: Mapped[DeviceInterface] = relationship(foreign_keys=[a_interface_id])
    b_interface: Mapped[DeviceInterface] = relationship(foreign_keys=[b_interface_id])


# --------------------------------------------------------------------------- assets & inventory

ASSET_STATUSES = (
    "received", "stored", "installed", "active", "quarantined",
    "in_repair", "pending_return", "returned", "decommissioned",
)


class Asset(TimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('received','stored','installed','active','quarantined','in_repair','pending_return','returned','decommissioned')",
            name="ck_assets_status",
        ),
        CheckConstraint("warranty_status IN ('known_active','known_expired','unknown')", name="ck_assets_warranty"),
        CheckConstraint(_origin_check, name="ck_assets_origin"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    display_id: Mapped[str] = mapped_column(String(32), unique=True)  # asset tag, e.g. NL-AST-0001
    serial_number: Mapped[str] = mapped_column(String(64), unique=True)
    asset_type: Mapped[str] = mapped_column(String(24))  # server | switch | psu | dimm | transceiver | patch_panel | pdu
    part_type_id: Mapped[Optional[int]] = mapped_column(ForeignKey("part_types.id", ondelete="SET NULL"), index=True)
    manufacturer: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="received", index=True)
    location: Mapped[str] = mapped_column(String(120), default="")
    installed_in_device_id: Mapped[Optional[int]] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), index=True)
    warranty_status: Mapped[str] = mapped_column(String(16), default="unknown")
    warranty_end: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    notes: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(16), default="seed")
    simulation_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    part_type: Mapped[Optional[PartType]] = relationship()
    installed_in: Mapped[Optional[Device]] = relationship(foreign_keys=[installed_in_device_id])


class PartType(TimestampMixin, Base):
    __tablename__ = "part_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    part_number: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(24))  # psu | dimm | transceiver | disk | cable
    connector_or_form: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    compatibility: Mapped[list[PartCompatibility]] = relationship(back_populates="part_type", cascade="all, delete-orphan")


class PartCompatibility(Base):
    __tablename__ = "part_compatibility"
    __table_args__ = (UniqueConstraint("part_type_id", "device_model", name="uq_compat_pair"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    part_type_id: Mapped[int] = mapped_column(ForeignKey("part_types.id", ondelete="CASCADE"), index=True)
    device_model: Mapped[str] = mapped_column(String(80), index=True)
    notes: Mapped[str] = mapped_column(String(200), default="")
    part_type: Mapped[PartType] = relationship(back_populates="compatibility")


class SpareStock(TimestampMixin, Base):
    """A stock location for a part type. Quantities are derived from the ledger; never stored."""

    __tablename__ = "spare_stock"
    __table_args__ = (
        UniqueConstraint("part_type_id", "location", name="uq_stock_part_location"),
        CheckConstraint("reorder_threshold >= 0", name="ck_stock_threshold"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    display_id: Mapped[str] = mapped_column(String(32), unique=True)
    part_type_id: Mapped[int] = mapped_column(ForeignKey("part_types.id", ondelete="RESTRICT"), index=True)
    location: Mapped[str] = mapped_column(String(120))
    reorder_threshold: Mapped[int] = mapped_column(Integer, default=1)
    part_type: Mapped[PartType] = relationship()


class Reservation(TimestampMixin, Base):
    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_reservation_qty"),
        CheckConstraint("status IN ('active','consumed','released')", name="ck_reservation_status"),
        CheckConstraint(_origin_check, name="ck_reservations_origin"),
        Index("ix_reservation_stock_status", "stock_id", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    display_id: Mapped[str] = mapped_column(String(32), unique=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("spare_stock.id", ondelete="RESTRICT"))
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="active")
    device_id: Mapped[Optional[int]] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    incident_id: Mapped[Optional[int]] = mapped_column(ForeignKey("incidents.id", ondelete="SET NULL"))
    reason: Mapped[str] = mapped_column(Text, default="")
    compatibility_exception: Mapped[bool] = mapped_column(Boolean, default=False)
    exception_reviewed_by: Mapped[str] = mapped_column(String(80), default="")
    exception_note: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(80), default="")
    consumed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    released_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    origin: Mapped[str] = mapped_column(String(16), default="operator")
    simulation_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    stock: Mapped[SpareStock] = relationship()
    device: Mapped[Optional[Device]] = relationship()


class InventoryTransaction(Base):
    """Immutable ledger row. On-hand quantity = SUM(quantity_delta) per stock row."""

    __tablename__ = "inventory_transactions"
    __table_args__ = (
        CheckConstraint("kind IN ('receive','consume','adjust','return_out','return_in')", name="ck_txn_kind"),
        CheckConstraint("quantity_delta <> 0", name="ck_txn_nonzero"),
        CheckConstraint(_origin_check, name="ck_txn_origin"),
        UniqueConstraint("reservation_id", "kind", name="uq_txn_reservation_kind"),  # no double consumption
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    display_id: Mapped[str] = mapped_column(String(32), unique=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("spare_stock.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    quantity_delta: Mapped[int] = mapped_column(Integer)
    reservation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("reservations.id", ondelete="SET NULL"))
    asset_id: Mapped[Optional[int]] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
    note: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(80), default="")
    origin: Mapped[str] = mapped_column(String(16), default="operator")
    simulation_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    stock: Mapped[SpareStock] = relationship()


class ReturnRecord(TimestampMixin, Base):
    __tablename__ = "return_records"
    __table_args__ = (
        CheckConstraint(
            "shipping_status IN ('awaiting_reference','ready_to_ship','shipped','received_by_vendor','closed')",
            name="ck_return_shipping",
        ),
        CheckConstraint("warranty_status IN ('known_active','known_expired','unknown')", name="ck_return_warranty"),
        CheckConstraint(_origin_check, name="ck_returns_origin"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    display_id: Mapped[str] = mapped_column(String(32), unique=True)
    failed_asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), unique=True)
    original_device_id: Mapped[Optional[int]] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    incident_id: Mapped[Optional[int]] = mapped_column(ForeignKey("incidents.id", ondelete="SET NULL"))
    failure_evidence_id: Mapped[Optional[int]] = mapped_column(ForeignKey("evidence_items.id", ondelete="SET NULL"))
    failure_summary: Mapped[str] = mapped_column(Text)
    warranty_status: Mapped[str] = mapped_column(String(16), default="unknown")
    return_reference: Mapped[Optional[str]] = mapped_column(String(64))  # recorded by operator; never fetched
    shipping_status: Mapped[str] = mapped_column(String(24), default="awaiting_reference")
    replacement_asset_id: Mapped[Optional[int]] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
    actor: Mapped[str] = mapped_column(String(80), default="")
    origin: Mapped[str] = mapped_column(String(16), default="operator")
    simulation_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    failed_asset: Mapped[Asset] = relationship(foreign_keys=[failed_asset_id])
    replacement_asset: Mapped[Optional[Asset]] = relationship(foreign_keys=[replacement_asset_id])
    original_device: Mapped[Optional[Device]] = relationship()


# --------------------------------------------------------------------------- incidents

INCIDENT_STATUSES = ("detected", "acknowledged", "investigating", "repair_applied", "verification", "resolved")


class Incident(TimestampMixin, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint("severity IN ('critical','major','minor')", name="ck_incident_severity"),
        CheckConstraint(
            "status IN ('detected','acknowledged','investigating','repair_applied','verification','resolved')",
            name="ck_incident_status",
        ),
        CheckConstraint(_src_check, name="ck_incident_source"),
        CheckConstraint(_origin_check, name="ck_incident_origin"),
        Index("ix_incident_status_severity", "status", "severity"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    display_id: Mapped[str] = mapped_column(String(32), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    symptom: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(16), default="detected", index=True)
    device_id: Mapped[Optional[int]] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), index=True)
    scenario_key: Mapped[Optional[str]] = mapped_column(String(48), index=True)
    runbook_slug: Mapped[Optional[str]] = mapped_column(String(64))
    detection_rule: Mapped[str] = mapped_column(String(200), default="")
    source_type: Mapped[str] = mapped_column(String(16))
    source_id: Mapped[str] = mapped_column(String(120))
    simulation_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    fault_onset_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)  # NULL = unknown onset
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    repair_applied_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    verified_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    assigned_operator: Mapped[Optional[str]] = mapped_column(String(80))
    reopen_count: Mapped[int] = mapped_column(Integer, default=0)
    root_cause: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(16), default="simulation")
    device: Mapped[Optional[Device]] = relationship()
    events: Mapped[list[IncidentEvent]] = relationship(back_populates="incident", order_by="IncidentEvent.id", cascade="all, delete-orphan")
    hypotheses: Mapped[list[Hypothesis]] = relationship(back_populates="incident", order_by="Hypothesis.id", cascade="all, delete-orphan")
    verifications: Mapped[list[Verification]] = relationship(back_populates="incident", order_by="Verification.id", cascade="all, delete-orphan")
    repairs: Mapped[list[RepairAction]] = relationship(back_populates="incident", order_by="RepairAction.id", cascade="all, delete-orphan")


class IncidentEvent(Base):
    """Append-only investigation timeline."""

    __tablename__ = "incident_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    kind: Mapped[str] = mapped_column(String(24))  # fault_onset|detected|status|evidence|hypothesis|repair|verification|reopened|note|resolved
    from_status: Mapped[Optional[str]] = mapped_column(String(16))
    to_status: Mapped[Optional[str]] = mapped_column(String(16))
    actor: Mapped[str] = mapped_column(String(80), default="system")
    summary: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    incident: Mapped[Incident] = relationship(back_populates="events")


class Hypothesis(TimestampMixin, Base):
    __tablename__ = "hypotheses"
    __table_args__ = (
        UniqueConstraint("incident_id", "key", name="uq_hypothesis_key"),
        CheckConstraint("status IN ('open','supported','refuted')", name="ck_hypothesis_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(48))
    statement: Mapped[str] = mapped_column(Text)
    discriminating_check: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="open")
    note: Mapped[str] = mapped_column(Text, default="")
    incident: Mapped[Incident] = relationship(back_populates="hypotheses")


class RepairAction(Base):
    __tablename__ = "repair_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    action_key: Mapped[str] = mapped_column(String(48))
    description: Mapped[str] = mapped_column(Text)
    applied_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    actor: Mapped[str] = mapped_column(String(80), default="")
    source_type: Mapped[str] = mapped_column(String(16))
    incident: Mapped[Incident] = relationship(back_populates="repairs")


class Verification(Base):
    __tablename__ = "verifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    executed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    after_repair_id: Mapped[Optional[int]] = mapped_column(ForeignKey("repair_actions.id", ondelete="SET NULL"))
    passed: Mapped[bool] = mapped_column(Boolean)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    source_type: Mapped[str] = mapped_column(String(16))
    source_id: Mapped[str] = mapped_column(String(120))
    incident: Mapped[Incident] = relationship(back_populates="verifications")


class EvidenceItem(Base):
    __tablename__ = "evidence_items"
    __table_args__ = (CheckConstraint(_src_check, name="ck_evidence_source"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    display_id: Mapped[str] = mapped_column(String(32), unique=True)
    incident_id: Mapped[Optional[int]] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    acceptance_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("acceptance_runs.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[Optional[int]] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), index=True)
    collector: Mapped[str] = mapped_column(String(48))  # e.g. systemctl_status
    command: Mapped[str] = mapped_column(String(300), default="")  # display only; never executed from input
    output: Mapped[str] = mapped_column(Text)
    observations: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # structured facts
    interpretation: Mapped[str] = mapped_column(Text, default="")  # what the output shows
    limitations: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(16))
    source_id: Mapped[str] = mapped_column(String(120))
    collected_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    simulation_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    origin: Mapped[str] = mapped_column(String(16), default="simulation")


class Runbook(TimestampMixin, Base):
    __tablename__ = "runbooks"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(160))
    project: Mapped[str] = mapped_column(String(48))
    symptom: Mapped[str] = mapped_column(Text)
    scenario_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    sections: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    version: Mapped[str] = mapped_column(String(16), default="1.0")


# --------------------------------------------------------------------------- acceptance


class AcceptanceProfile(TimestampMixin, Base):
    __tablename__ = "acceptance_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(48), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[str] = mapped_column(String(16), default="1.0")
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSON)  # [{check_key, required}]


class IntakeRecord(TimestampMixin, Base):
    __tablename__ = "intake_records"
    __table_args__ = (
        CheckConstraint(_src_check, name="ck_intake_source"),
        CheckConstraint(_origin_check, name="ck_intake_origin"),
        CheckConstraint(
            "status IN ('awaiting_acceptance','failed','manual_review','accepted','handed_off')",
            name="ck_intake_status",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    display_id: Mapped[str] = mapped_column(String(32), unique=True)
    asset_id: Mapped[Optional[int]] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
    device_id: Mapped[Optional[int]] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    asset_tag: Mapped[str] = mapped_column(String(32))
    serial_number: Mapped[str] = mapped_column(String(64))
    hostname: Mapped[str] = mapped_column(String(120))
    expected: Mapped[dict[str, Any]] = mapped_column(JSON)  # cpu_count, cpu_model, memory_gib, storage[], nic_count, data_link_speed_mbps
    intended_rack_id: Mapped[Optional[int]] = mapped_column(ForeignKey("racks.id", ondelete="SET NULL"))
    intended_position_u: Mapped[Optional[int]] = mapped_column(Integer)
    profile_id: Mapped[int] = mapped_column(ForeignKey("acceptance_profiles.id", ondelete="RESTRICT"))
    source_type: Mapped[str] = mapped_column(String(16), default="SIMULATED")
    status: Mapped[str] = mapped_column(String(24), default="awaiting_acceptance")
    operator: Mapped[str] = mapped_column(String(80), default="")
    # Simulator model of this machine's hardware (only used by the simulator collector).
    simulated_hardware: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    simulated_corrections: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # Last uploaded real observation set (Linux collector / imported sample), sanitized.
    uploaded_observations: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    uploaded_source_type: Mapped[Optional[str]] = mapped_column(String(16))
    origin: Mapped[str] = mapped_column(String(16), default="seed")
    simulation_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    profile: Mapped[AcceptanceProfile] = relationship()
    runs: Mapped[list[AcceptanceRun]] = relationship(back_populates="intake", order_by="AcceptanceRun.run_number")
    intended_rack: Mapped[Optional[Rack]] = relationship()


class AcceptanceRun(Base):
    __tablename__ = "acceptance_runs"
    __table_args__ = (
        UniqueConstraint("intake_id", "run_number", name="uq_run_number"),
        CheckConstraint("status IN ('queued','running','completed','error')", name="ck_run_status"),
        CheckConstraint("disposition IS NULL OR disposition IN ('PASS','FAIL','MANUAL_REVIEW')", name="ck_run_disposition"),
        CheckConstraint(_src_check, name="ck_run_source"),
        CheckConstraint(_origin_check, name="ck_run_origin"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    display_id: Mapped[str] = mapped_column(String(32), unique=True)
    intake_id: Mapped[int] = mapped_column(ForeignKey("intake_records.id", ondelete="CASCADE"), index=True)
    run_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    disposition: Mapped[Optional[str]] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    operator: Mapped[str] = mapped_column(String(80), default="")
    collector: Mapped[str] = mapped_column(String(48))  # simulator | linux_upload | redfish_fixture | redfish_live
    source_type: Mapped[str] = mapped_column(String(16))
    source_id: Mapped[str] = mapped_column(String(120))
    expected_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    observed_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    corrections_before_run: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    manual_reviews: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    follow_up_actions: Mapped[list[str]] = mapped_column(JSON, default=list)
    origin: Mapped[str] = mapped_column(String(16), default="operator")
    simulation_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    intake: Mapped[IntakeRecord] = relationship(back_populates="runs")
    results: Mapped[list[AcceptanceCheckResult]] = relationship(back_populates="run", order_by="AcceptanceCheckResult.id", cascade="all, delete-orphan")


class AcceptanceCheckResult(Base):
    __tablename__ = "acceptance_check_results"
    __table_args__ = (
        UniqueConstraint("run_id", "check_key", name="uq_result_check"),
        CheckConstraint(
            "result IN ('PASS','FAIL','MANUAL_REVIEW','UNSUPPORTED','SKIPPED','ERROR')", name="ck_result_value"
        ),
        CheckConstraint(_src_check, name="ck_result_source"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("acceptance_runs.id", ondelete="CASCADE"), index=True)
    check_key: Mapped[str] = mapped_column(String(48))
    check_name: Mapped[str] = mapped_column(String(120))
    check_version: Mapped[str] = mapped_column(String(16))
    required: Mapped[bool] = mapped_column(Boolean)
    result: Mapped[str] = mapped_column(String(16))
    expected_value: Mapped[Optional[str]] = mapped_column(Text)
    observed_value: Mapped[Optional[str]] = mapped_column(Text)
    unit: Mapped[Optional[str]] = mapped_column(String(24))
    detail: Mapped[str] = mapped_column(Text, default="")
    evidence_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("evidence_items.id", ondelete="SET NULL"))
    executed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    source_type: Mapped[str] = mapped_column(String(16))
    run: Mapped[AcceptanceRun] = relationship(back_populates="results")


# --------------------------------------------------------------------------- platform


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        CheckConstraint(_origin_check, name="ck_audit_origin"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int] = mapped_column(Integer)
    entity_display: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(Text)
    before: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    after: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    related: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)  # [{type,id,display}]
    origin: Mapped[str] = mapped_column(String(16), default="operator")
    simulation_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running','paused','awaiting_operator','completed','cancelled')", name="ck_sim_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    display_id: Mapped[str] = mapped_column(String(32), unique=True)
    scenario_key: Mapped[str] = mapped_column(String(48), index=True)
    demo_key: Mapped[Optional[str]] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(20), default="running")
    phase: Mapped[str] = mapped_column(String(32), default="baseline")
    probe_count: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    next_tick_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    paused_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    device_id: Mapped[Optional[int]] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    incident_id: Mapped[Optional[int]] = mapped_column(Integer)  # soft link (avoid FK cycle)


class MetricObservation(Base):
    __tablename__ = "metric_observations"
    __table_args__ = (
        Index("ix_metric_device_metric_time", "device_id", "metric", "observed_at"),
        CheckConstraint(_src_check, name="ck_metric_source"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[Optional[int]] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    metric: Mapped[str] = mapped_column(String(48))
    value: Mapped[Optional[float]] = mapped_column(Float)  # NULL = not collected (never coerced to 0)
    unit: Mapped[str] = mapped_column(String(24))
    labels: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    source_type: Mapped[str] = mapped_column(String(16))
    source_id: Mapped[str] = mapped_column(String(120))
    simulation_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)


class StreamEvent(Base):
    """Persisted SSE events so clients can resume with Last-Event-ID."""

    __tablename__ = "stream_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    topic: Mapped[str] = mapped_column(String(48))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("key", "endpoint", name="uq_idem_key_endpoint"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(128))
    endpoint: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict[str, Any]] = mapped_column(JSON)
    status_code: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class CandidateProfile(TimestampMixin, Base):
    __tablename__ = "candidate_profile"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="[Candidate Name]")
    headline: Mapped[str] = mapped_column(String(200), default="Data Center Operations Technician — interview portfolio")
    summary: Mapped[str] = mapped_column(Text, default="")
    links: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    operator_name: Mapped[str] = mapped_column(String(80), default="operator")


class ProjectNote(TimestampMixin, Base):
    __tablename__ = "project_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(48), unique=True)
    candidate_contribution: Mapped[str] = mapped_column(Text, default="")
    lessons_learned: Mapped[str] = mapped_column(Text, default="")


class LabSetting(Base):
    __tablename__ = "lab_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class DisplayCounter(Base):
    """Monotonic counters for readable display IDs (INC-0001 etc.)."""

    __tablename__ = "display_counters"
    prefix: Mapped[str] = mapped_column(String(16), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)
