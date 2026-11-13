"""Vercel serverless entrypoint for the RackOps Lab API (hosted demo mode).

Serverless hosts have no long-running process and an ephemeral filesystem, so this entrypoint
creates and seeds a SQLite database in /tmp on cold start. Simulation work is advanced by
incoming requests and the event stream (see RACKOPS_SERVERLESS in app/config.py).
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("RACKOPS_SERVERLESS", "true")
os.environ.setdefault("RACKOPS_RUNNER_ENABLED", "false")
os.environ.setdefault("RACKOPS_DATABASE_URL", "sqlite:////tmp/rackops.db")

from app import models  # noqa: E402,F401  (register tables)
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.seed import seed  # noqa: E402

Base.metadata.create_all(engine)
with SessionLocal() as _db:
    seed(_db)  # no-op when this instance is already seeded

from app.main import app  # noqa: E402,F401
