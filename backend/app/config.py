"""Runtime configuration. All secrets come from the environment, never source control."""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BASE_DIR.parent / ".env"), env_prefix="RACKOPS_", extra="ignore")

    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'rackops.db'}"
    bind_host: str = "127.0.0.1"
    frontend_origin: str = "http://localhost:5173"
    public_base_url: str = "http://localhost:5173"

    # Job runner
    runner_enabled: bool = True
    runner_tick_seconds: float = 1.0
    sim_probe_interval_seconds: float = 3.0

    # Read-only public preview: disables every mutation and collection endpoint.
    public_preview: bool = False

    # Upload limits
    max_upload_bytes: int = 512 * 1024

    # Optional: live lab target (a self-owned HTTP process on localhost)
    livelab_port: int = 18081

    # Optional Redfish (read-only). Empty URL = fixture mode.
    redfish_url: str = ""
    redfish_username: str = ""
    redfish_password: str = Field(default="", repr=False)
    redfish_verify_tls: bool = True
    redfish_timeout_seconds: float = 5.0

    # Optional NetBox (read-only import)
    netbox_url: str = ""
    netbox_token: str = Field(default="", repr=False)

    # Optional Alertmanager webhook receiver (disabled by default)
    alertmanager_webhook_enabled: bool = False
    alertmanager_webhook_token: str = Field(default="", repr=False)

    # Jira export is file-based; an API adapter is only "configured" if both are set.
    jira_url: str = ""
    jira_token: str = Field(default="", repr=False)

    # External notifications (disabled by default; none implemented beyond flag)
    notifications_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
