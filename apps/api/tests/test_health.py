from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_liveness() -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api", "version": "0.1.0"}


def test_readiness() -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["checks"] == {"api": "ok"}


def test_openapi_exposes_health_contract() -> None:
    schema = client.get("/openapi.json").json()
    assert "/health/live" in schema["paths"]
    assert schema["info"]["title"] == "Vocal Score Studio API"
