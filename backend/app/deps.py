from fastapi import Depends, Header
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .services import common


def require_mutations() -> None:
    """Public preview mode disables every mutation and collection endpoint."""
    if get_settings().public_preview:
        raise common.DomainError("read_only_preview", "This is a read-only public preview; mutations are disabled.", 403)


def actor(db: Session = Depends(get_db)) -> str:
    return common.operator_name(db)


IdemKey = Header(default=None, alias="Idempotency-Key", max_length=128)
