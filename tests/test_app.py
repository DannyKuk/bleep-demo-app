import time

import pytest
from fastapi.testclient import TestClient

from demo_app import faults
from demo_app.app import create_app
from demo_app.config import Settings, load_settings, parse_fail_after

PASSWORD = "s3cret"


def client_for(**overrides) -> TestClient:
    settings = Settings(demo_password=overrides.pop("demo_password", PASSWORD), **overrides)
    return TestClient(create_app(settings))


def trigger(client: TestClient, fault: str, password: str | None = PASSWORD):
    body = {} if password is None else {"password": password}
    return client.post(f"/api/faults/{fault}", json=body)


def test_health_ok_and_page_public():
    with client_for(demo_password=None) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/health").status_code == 200
        page = client.get("/")
        assert page.status_code == 200
        assert "<html" in page.text


def test_wrong_and_missing_password_rejected():
    with client_for() as client:
        assert trigger(client, "error", "nope").status_code == 401
        assert trigger(client, "error", None).status_code == 401
        assert client.get("/health").status_code == 200


def test_faults_disabled_when_password_unset():
    with client_for(demo_password=None) as client:
        assert trigger(client, "error", "").status_code == 403
        assert client.get("/api/status").json()["faults_enabled"] is False
        assert client.get("/health").status_code == 200


def test_error_fault_makes_health_500_and_logs(caplog):
    with client_for() as client:
        assert trigger(client, "error").status_code == 200
        with caplog.at_level("ERROR"):
            assert client.get("/health").status_code == 500
            assert client.get("/health").status_code == 500
    logged = [r.getMessage() for r in caplog.records if "connection pool exhausted" in r.getMessage()]
    assert len(logged) >= 2
    assert client.get("/health").status_code == 500


def test_fail_after_turns_unhealthy_and_names_the_setting(caplog):
    with client_for(fail_after_s=0.2) as client:
        assert client.get("/health").status_code == 200
        time.sleep(0.3)
        with caplog.at_level("ERROR"):
            assert client.get("/health").status_code == 500
    assert any("FAIL_AFTER_S=0.2" in r.getMessage() for r in caplog.records)


def test_status_shows_config_faults_without_secrets():
    with client_for(host="127.0.0.1", fail_after_s=30) as client:
        status = client.get("/api/status").json()
    assert status["config"] == {"host": "127.0.0.1", "host_is_loopback": True, "fail_after_s": 30}
    assert PASSWORD not in str(status)


@pytest.mark.parametrize("fault", ["hang", "crash"])
def test_hang_and_crash_call_their_handler(monkeypatch, fault):
    calls = []
    monkeypatch.setattr(faults, fault, lambda: calls.append(fault))
    with client_for() as client:
        assert trigger(client, fault).status_code == 200
        time.sleep(0.4)
    assert calls == [fault]


def test_leak_starts_the_leak_once(monkeypatch):
    started = []

    async def fake_run(self):
        started.append(self)

    monkeypatch.setattr(faults.Leak, "run", fake_run)
    with client_for() as client:
        assert trigger(client, "leak").status_code == 200
        assert trigger(client, "leak").status_code == 200
        time.sleep(0.1)
    assert len(started) == 1


def test_parse_fail_after():
    assert parse_fail_after(None) is None
    assert parse_fail_after("") is None
    assert parse_fail_after("0") is None
    assert parse_fail_after("45") == 45
    with pytest.raises(ValueError, match="FAIL_AFTER_S"):
        parse_fail_after("soon")
    with pytest.raises(ValueError, match="FAIL_AFTER_S"):
        parse_fail_after("-1")


def test_load_settings_defaults_and_overrides():
    defaults = load_settings({})
    assert (defaults.host, defaults.port, defaults.fail_after_s, defaults.demo_password) == (
        "0.0.0.0",
        3000,
        None,
        None,
    )
    assert not defaults.host_is_loopback
    custom = load_settings({"HOST": "127.0.0.1", "PORT": "8080", "FAIL_AFTER_S": "10", "DEMO_PASSWORD": "x"})
    assert custom.host_is_loopback
    assert (custom.port, custom.fail_after_s, custom.demo_password) == (8080, 10, "x")
    assert load_settings({"HOST": "", "DEMO_PASSWORD": ""}).demo_password is None
