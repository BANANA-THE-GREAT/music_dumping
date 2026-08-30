import time
from io import BytesIO

from app.job_runner import recover_interrupted_thread_jobs
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
    assert job["status"] in {"queued", "running"}
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        current = client.get(f"/v1/jobs/{job['id']}").json()
        if current["status"] == "completed":
            break
        time.sleep(0.03)
    assert current["status"] == "completed"
    project = client.get(f"/v1/projects/{current['project_id']}")
    assert project.status_code == 200
    assert len(project.json()["notes"]) == 11


def test_job_can_be_cancelled() -> None:
    upload = create_test_upload()
    job = client.post(
        "/v1/jobs", json={"upload_id": upload["id"], "options": {"auto_start": False}}
    ).json()
    response = client.post(f"/v1/jobs/{job['id']}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    retry = client.post(f"/v1/jobs/{job['id']}/retry")
    assert retry.status_code == 202
    assert retry.json()["upload_id"] == upload["id"]
    assert retry.json()["status"] == "queued"


def test_running_job_cannot_be_retried() -> None:
    upload = create_test_upload()
    job = client.post(
        "/v1/jobs", json={"upload_id": upload["id"], "options": {"auto_start": False}}
    ).json()
    assert client.post(f"/v1/jobs/{job['id']}/retry").status_code == 409
    assert client.post(f"/v1/jobs/{job['id']}/cancel").status_code == 200


def test_interrupted_local_job_becomes_retryable() -> None:
    upload = create_test_upload()
    job = client.post(
        "/v1/jobs", json={"upload_id": upload["id"], "options": {"auto_start": False}}
    ).json()
    assert recover_interrupted_thread_jobs() >= 1
    recovered = client.get(f"/v1/jobs/{job['id']}").json()
    assert recovered["status"] == "failed"
    assert recovered["error_code"] == "WORKER_RESTARTED"
    assert recovered["retryable"] is True


def test_rejects_unsupported_upload() -> None:
    response = client.post(
        "/v1/uploads", files={"file": ("notes.txt", BytesIO(b"not audio"), "text/plain")}
    )
    assert response.status_code == 415


def test_rejects_job_for_unknown_upload() -> None:
    assert client.post("/v1/jobs", json={"upload_id": "missing"}).status_code == 404


def test_job_events_end_with_completed_state() -> None:
    upload = create_test_upload()
    job = client.post("/v1/jobs", json={"upload_id": upload["id"]}).json()
    with client.stream("GET", f"/v1/jobs/{job['id']}/events") as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert "event: progress" in body
    assert '"status":"completed"' in body
