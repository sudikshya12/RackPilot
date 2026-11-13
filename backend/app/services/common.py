"""Cross-cutting helpers: display IDs, audit trail, errors, stream events, idempotency."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..models import utcnow


class DomainError(Exception):
    """A rule violation that maps to a consistent API error envelope."""

    def __init__(self, code: str, message: str, status: int = 409, detail: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.detail = detail or {}


class NotFound(DomainError):
    def __init__(self, what: str, ident: Any):
        super().__init__("not_found", f"{what} {ident} was not found", 404)


def next_display_id(db: Session, prefix: str, width: int = 4) -> str:
    counter = db.get(m.DisplayCounter, prefix)
    if counter is None:
        counter = m.DisplayCounter(prefix=prefix, value=0)
        db.add(counter)
    counter.value += 1
    db.flush()
    return f"{prefix}-{counter.value:0{width}d}"


def get_or_404(db: Session, model, ident: Any, what: Optional[str] = None):
    obj = None
    if isinstance(ident, int) or (isinstance(ident, str) and ident.isdigit()):
        obj = db.get(model, int(ident))
    if obj is None and hasattr(model, "display_id"):
        obj = db.scalar(select(model).where(model.display_id == str(ident)))
    if obj is None:
        raise NotFound(what or model.__name__, ident)
    return obj


def audit(
    db: Session,
    *,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: int,
    entity_display: str,
    summary: str,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    related: Optional[list[dict]] = None,
    origin: str = "operator",
    simulation_run_id: Optional[int] = None,
    at: Optional[datetime] = None,
) -> m.AuditEvent:
    ev = m.AuditEvent(
        occurred_at=at or utcnow(),
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_display=entity_display,
        summary=summary,
        before=before,
        after=after,
        related=related or [],
        origin=origin,
        simulation_run_id=simulation_run_id,
    )
    db.add(ev)
    db.flush()
    publish(db, "audit", {"id": ev.id, "entity_type": entity_type, "entity_id": entity_id, "action": action})
    return ev


def publish(db: Session, topic: str, payload: dict[str, Any]) -> None:
    """Persist a stream event inside the caller's transaction; the SSE endpoint tails the table."""
    db.add(m.StreamEvent(topic=topic, payload=payload, created_at=utcnow()))


def get_setting(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(m.LabSetting, key)
    return row.value if row else default


def set_setting(db: Session, key: str, value: Any) -> None:
    row = db.get(m.LabSetting, key)
    if row:
        row.value = value
    else:
        db.add(m.LabSetting(key=key, value=value))


def operator_name(db: Session) -> str:
    prof = db.scalar(select(m.CandidateProfile).limit(1))
    return prof.operator_name if prof else "operator"


# ----------------------------------------------------------------- idempotency


def _hash(body: Any) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def idempotent_lookup(db: Session, key: Optional[str], endpoint: str, body: Any):
    """Return a stored (status, response) when the key was already used for this endpoint."""
    if not key:
        return None
    row = db.scalar(select(m.IdempotencyKey).where(m.IdempotencyKey.key == key, m.IdempotencyKey.endpoint == endpoint))
    if row is None:
        return None
    if row.request_hash != _hash(body):
        raise DomainError(
            "idempotency_conflict",
            "This Idempotency-Key was already used with a different request body.",
            422,
        )
    return row.status_code, row.response


def idempotent_store(db: Session, key: Optional[str], endpoint: str, body: Any, status: int, response: Any) -> None:
    if not key:
        return
    db.add(m.IdempotencyKey(key=key, endpoint=endpoint, request_hash=_hash(body), response=response, status_code=status))


def dt(v: Optional[datetime]) -> Optional[str]:
    return v.isoformat().replace("+00:00", "Z") if v else None
