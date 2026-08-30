import time
from io import BytesIO

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def create_project() -> dict[str, object]:
    upload = client.post(
        "/v1/uploads",
        files={"file": ("edit.wav", BytesIO(b"RIFF-edit-audio"), "audio/wav")},
    ).json()
    job = client.post("/v1/jobs", json={"upload_id": upload["id"]}).json()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = client.get(f"/v1/jobs/{job['id']}").json()
        if job["status"] == "completed":
            break
        time.sleep(0.03)
    assert job["status"] == "completed"
    return client.get(f"/v1/projects/{job['project_id']}").json()


def test_project_edit_uses_optimistic_revision() -> None:
    project = create_project()
    notes = project["notes"]
    notes[0]["pitch_midi"] = 72
    notes[0]["origin"] = "user"

    response = client.patch(
        f"/v1/projects/{project['project_id']}",
        json={"expected_revision": project["revision"], "notes": notes},
    )
    assert response.status_code == 200
    assert response.json()["revision"] == 2
    assert response.json()["notes"][0]["pitch_midi"] == 72

    stale = client.patch(
        f"/v1/projects/{project['project_id']}",
        json={"expected_revision": project["revision"], "notes": notes},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "REVISION_CONFLICT"


def test_project_can_be_requantized() -> None:
    project = create_project()
    response = client.post(
        f"/v1/projects/{project['project_id']}/requantize",
        json={
            "expected_revision": project["revision"],
            "bpm": 90,
            "numerator": 3,
            "denominator": 4,
            "tonic": 7,
            "mode": "minor",
            "grid": 0.5,
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["revision"] == 2
    assert result["analysis"]["tempo_map"][0]["bpm"] == 90
    assert result["analysis"]["meter_map"][0]["numerator"] == 3
    assert result["analysis"]["key_map"][0]["tonic"] == 7
    assert result["pipeline"][-1]["stage"] == "requantize"
