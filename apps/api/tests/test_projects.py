import time
from io import BytesIO

from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models import JobRecord, ProjectRecord, UploadRecord
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


def test_project_exports_standard_midi_and_musicxml() -> None:
    project = create_project()
    project_id = project["project_id"]

    midi = client.get(f"/v1/projects/{project_id}/exports/midi")
    assert midi.status_code == 200
    assert midi.content.startswith(b"MThd")
    assert b"MTrk" in midi.content
    assert midi.headers["content-disposition"].endswith(f'"{project_id}.mid"')

    musicxml = client.get(f"/v1/projects/{project_id}/exports/musicxml")
    assert musicxml.status_code == 200
    assert b'<score-partwise version="4.0">' in musicxml.content
    assert musicxml.content.count(b"<note>") >= len(project["notes"])
    assert musicxml.content.count(b"<measure ") == 3

    audio = client.get(f"/v1/projects/{project_id}/audio")
    assert audio.status_code == 200
    assert audio.content == b"RIFF-edit-audio"
    assert audio.headers["content-type"].startswith("audio/wav")


def test_projects_are_listed_for_reopening() -> None:
    project = create_project()
    response = client.get("/v1/projects")
    assert response.status_code == 200
    matching = [item for item in response.json() if item["project_id"] == project["project_id"]]
    assert matching == [
        {
            "project_id": project["project_id"],
            "file_name": "edit.wav",
            "duration_ms": 6000,
            "note_count": 11,
            "revision": 1,
            "updated_at": matching[0]["updated_at"],
        }
    ]


def test_project_deletion_removes_related_records_and_source_file() -> None:
    project = create_project()
    source_path = get_settings().data_dir / project["source"]["audio_object_key"]
    assert source_path.exists()
    with SessionLocal() as session:
        record = session.get(ProjectRecord, project["project_id"])
        job_id = record.job_id
        upload_id = session.get(JobRecord, job_id).upload_id

    response = client.delete(f"/v1/projects/{project['project_id']}")
    assert response.status_code == 204
    assert client.get(f"/v1/projects/{project['project_id']}").status_code == 404
    assert not source_path.exists()
    assert project["project_id"] not in {
        item["project_id"] for item in client.get("/v1/projects").json()
    }
    with SessionLocal() as session:
        assert session.get(ProjectRecord, project["project_id"]) is None
        assert session.get(JobRecord, job_id) is None
        assert session.get(UploadRecord, upload_id) is None


def test_project_deletion_preserves_upload_used_by_another_job() -> None:
    project = create_project()
    source_path = get_settings().data_dir / project["source"]["audio_object_key"]
    with SessionLocal() as session:
        record = session.get(ProjectRecord, project["project_id"])
        job_id = record.job_id
        upload_id = session.get(JobRecord, job_id).upload_id
    other_job = client.post(
        "/v1/jobs", json={"upload_id": upload_id, "options": {"auto_start": False}}
    ).json()

    assert client.delete(f"/v1/projects/{project['project_id']}").status_code == 204
    assert source_path.exists()
    with SessionLocal() as session:
        assert session.get(ProjectRecord, project["project_id"]) is None
        assert session.get(JobRecord, job_id) is None
        assert session.get(JobRecord, other_job["id"]) is not None
        assert session.get(UploadRecord, upload_id) is not None


def test_melody_refinement_preserves_raw_notes_and_revision() -> None:
    project = create_project()
    path = f"/v1/projects/{project['project_id']}/melody"
    refined = client.post(path, json={"expected_revision": 1, "mode": "balanced"})
    assert refined.status_code == 200
    assert refined.json()["raw_notes"] == project["notes"]
    assert client.post(path, json={"expected_revision": 1}).status_code == 409
    restored = client.post(path, json={"expected_revision": 2, "mode": "raw"})
    assert restored.status_code == 200
    assert restored.json()["notes"] == project["notes"]
    assert (
        client.post(
            path, json={"expected_revision": 3, "low_pitch": 90, "high_pitch": 50}
        ).status_code
        == 422
    )


def test_vocal_preview_serves_actual_stem_and_handles_legacy_path() -> None:
    project = create_project()
    path = f"/v1/projects/{project['project_id']}/audio?variant=vocals"
    assert client.get(path).status_code == 404
    with SessionLocal() as session:
        record = session.get(ProjectRecord, project["project_id"])
        stem = (
            get_settings().data_dir
            / "work"
            / record.job_id
            / "stems/htdemucs/normalized/vocals.wav"
        )
        stem.parent.mkdir(parents=True)
        stem.write_bytes(b"RIFF-separated-vocals")
        doc = dict(record.document)
        doc["source"] = {**doc["source"], "vocal_object_key": "work/old-project/vocals.wav"}
        record.document = doc
        session.commit()
    response = client.get(path)
    assert response.status_code == 200
    assert response.content == b"RIFF-separated-vocals"
    assert response.headers["content-type"].startswith("audio/wav")
