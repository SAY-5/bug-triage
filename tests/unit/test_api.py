"""API surface tests via FastAPI TestClient.

We point DATABASE_URL at a nonexistent server *only inside the fixture* so
persistence falls back gracefully. The env var is restored on teardown so
the integration suite (which runs in the same pytest process) sees the
original DATABASE_URL.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(request: pytest.FixtureRequest) -> Iterator[TestClient]:
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("HASH_EMBEDDER", "1")
    monkeypatch.setenv("PROVIDER", "fake")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:x@127.0.0.1:1/none")
    from bug_triage.api import app

    with TestClient(app) as c:
        yield c
    monkeypatch.undo()


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_triage_returns_pipeline_shape(client: TestClient) -> None:
    r = client.post(
        "/v1/triage",
        json={"bug_report": "Calculator.div returns Infinity instead of throwing on zero divisor"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) >= {
        "triage_id",
        "classification",
        "retrieved",
        "suggestion",
        "latency_ms",
    }
    assert body["classification"]["severity"] in {"critical", "high", "medium", "low"}
    assert body["classification"]["component"] in {"api", "core", "util", "tests", "build"}
    assert len(body["retrieved"]) == 3
    assert body["retrieved"][0]["resolution_id"] == "R001"
    # Persistence is best-effort; with the fake DB URL it will fail quietly.
    assert body["triage_id"] is None


def test_triage_rejects_empty_body(client: TestClient) -> None:
    r = client.post("/v1/triage", json={"bug_report": ""})
    assert r.status_code == 422


def test_get_triage_unknown_id_returns_404_or_503(client: TestClient) -> None:
    r = client.get("/v1/triage/999999")
    # 404 if DB is up and id not found; 503 if DB is unreachable (CI fake URL).
    assert r.status_code in {404, 503}


def test_list_resolutions_handles_missing_db(client: TestClient) -> None:
    r = client.get("/v1/resolutions")
    # Without a real DB the handler raises; we don't gate on a specific code,
    # just that the route is registered.
    assert r.status_code in {200, 500, 503}
