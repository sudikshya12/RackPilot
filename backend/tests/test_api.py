def test_openapi_and_error_envelope(client):
    spec = client.get("/api/openapi.json").json()
    assert "/api/incidents" in spec["paths"] and "/api/reservations/{rid}/consume" in spec["paths"]
    r = client.get("/api/incidents/INC-9999")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = client.post("/api/reservations", json={"stock_id": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_overview_counts_match_records(client):
    ov = client.get("/api/overview").json()
    devs = client.get("/api/devices?role=server,switch").json()
    assert ov["devices"]["total"] == len(devs)
    assert ov["devices"]["healthy"] == sum(1 for d in devs if d["health"] == "healthy")
    spares = client.get("/api/spares").json()["stock"]
    assert ov["low_stock"]["total"] == sum(1 for s in spares if s["low_stock"])


def test_settings_never_returns_credentials(client, monkeypatch):
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("RACKOPS_REDFISH_PASSWORD", "super-secret-pw")
    monkeypatch.setenv("RACKOPS_REDFISH_USERNAME", "admin")
    try:
        body = client.get("/api/settings").text
        assert "super-secret-pw" not in body
    finally:
        get_settings.cache_clear()


def test_alertmanager_disabled_by_default(client):
    r = client.post("/api/integrations/alertmanager", json={"status": "firing", "alerts": []})
    assert r.status_code == 403


def test_public_preview_blocks_mutations(client, monkeypatch):
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("RACKOPS_PUBLIC_PREVIEW", "true")
    try:
        assert client.post("/api/scenarios/svc-stopped/start").status_code == 403
        assert client.get("/api/incidents").status_code == 200
    finally:
        get_settings.cache_clear()
