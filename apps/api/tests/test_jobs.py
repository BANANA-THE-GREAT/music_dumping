from io import BytesIO

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def create_test_upload() -> dict[str, object]:
    response = client.post(
        "/v1/uploads", files={"file": ("voice.wav", BytesIO(b"RIFF-test-audio"), "audio/wav")}
    )
    assert response.status_code == 201
    return response.json()


def test_upload_and_submit_job() -> None:
    upload = create_test_upload()
    response = client.post("/v1/jobs", json={"upload_id": upload["id"]})
    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "queued"
    assert job["stage"] == "queued"
    assert client.get(f"/v1/jobs/{job['id']}").json() == job


def test_job_can_be_cancelled() -> None:
    upload = create_test_upload()
    job = client.post("/v1/jobs", json={"upload_id": upload["id"]}).json()
    response = client.post(f"/v1/jobs/{job['id']}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_rejects_unsupported_upload() -> None:
    response = client.post(
        "/v1/uploads", files={"file": ("notes.txt", BytesIO(b"not audio"), "text/plain")}
    )
    assert response.status_code == 415


def test_rejects_job_for_unknown_upload() -> None:
    assert client.post("/v1/jobs", json={"upload_id": "missing"}).status_code == 404
