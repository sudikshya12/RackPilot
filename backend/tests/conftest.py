import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ["RACKOPS_RUNNER_ENABLED"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db as dbmod  # noqa: E402
from app import models as m  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = dbmod.configure(url)
    from alembic import command
    from alembic.config import Config
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    command.upgrade(cfg, "head")
    from app.seed import seed
    s = dbmod.SessionLocal()
    seed(s)
    yield s
    s.close()
    engine.dispose()


@pytest.fixture()
def client(db):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


class Clock:
    def __init__(self):
        self.t = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.t

    def advance(self, s: float):
        self.t += timedelta(seconds=s)
        return self.t


@pytest.fixture()
def clock():
    return Clock()


def run_until_incident(db, run, clock, max_ticks=40):
    from app.services import simulation
    for _ in range(max_ticks):
        simulation.tick(db, clock())
        db.flush()
        if run.incident_id:
            return db.get(m.Incident, run.incident_id)
        clock.advance(3)
    raise AssertionError("no incident detected")


def advance_probes(db, clock, n):
    from app.services import simulation
    for _ in range(n):
        clock.advance(3)
        simulation.tick(db, clock())
        db.flush()
