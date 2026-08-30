import time
from io import BytesIO

from app.config import get_settings
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_upload_to_export_and_delete_workflow() -> None:
    upload_response = client.post(
        "/v1/uploads",
        files={"file": ("workflow.wav", BytesIO(b"RIFF-workflow-audio"), "audio/wav")},
    )
    assert upload_response.status_code == 201
    upload = upload_response.json()

    job_response = client.post("/v1/jobs", json={"upload_id": upload["id"]})
    assert job_response.status_code == 202
    job = job_response.json()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = client.get(f"/v1/jobs/{job['id']}").json()
        if job["status"] == "completed":
            break
        time.sleep(0.03)
    assert job["status"] == "completed"

    project_id = job["project_id"]
    project = client.get(f"/v1/projects/{project_id}").json()
    source_path = get_settings().data_dir / project["source"]["audio_object_key"]
    project["notes"][0]["pitch_midi"] += 1
    project["notes"][0]["origin"] = "user"
    edited_response = client.patch(
        f"/v1/projects/{project_id}",
        json={"expected_revision": project["revision"], "notes": project["notes"]},
    )
    assert edited_response.status_code == 200
    edited = edited_response.json()
    assert edited["revision"] == project["revision"] + 1

    requantized_response = client.post(
        f"/v1/projects/{project_id}/requantize",
        json={
            "expected_revision": edited["revision"],
            "bpm": 96,
            "numerator": 6,
            "denominator": 8,
            "tonic": 9,
            "mode": "minor",
            "grid": 0.25,
        },
    )
    assert requantized_response.status_code == 200
    requantized = requantized_response.json()
    assert requantized["revision"] == edited["revision"] + 1
    assert requantized["analysis"]["meter_map"][0]["numerator"] == 6

    midi = client.get(f"/v1/projects/{project_id}/exports/midi")
    musicxml = client.get(f"/v1/projects/{project_id}/exports/musicxml")
    assert midi.status_code == 200 and midi.content.startswith(b"MThd")
    assert musicxml.status_code == 200 and b"<score-partwise" in musicxml.content

    assert client.delete(f"/v1/projects/{project_id}").status_code == 204
    assert client.get(f"/v1/projects/{project_id}").status_code == 404
    assert client.get(f"/v1/projects/{project_id}/audio").status_code == 404
    assert not source_path.exists()
