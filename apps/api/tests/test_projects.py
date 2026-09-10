import time
from copy import deepcopy
from io import BytesIO

from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models import JobRecord, ProjectRecord, UploadRecord
from app.schemas import ScoreProject
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


def add_boundary_evidence(project: dict[str, object]) -> list[dict[str, object]]:
    notes = project["notes"]
    performance_notes = project["performance_notes"]
    assert isinstance(notes, list)
    assert isinstance(performance_notes, list)
    suggestions = []
    for index, (note, performance_note) in enumerate(
        zip(notes[:2], performance_notes[:2], strict=True)
    ):
        source_id = f"source-{index}"
        note["source_note_ids"] = [source_id]
        performance_note["source_note_ids"] = [source_id]
        suggestions.append(
            {
                "id": f"boundary-{index}",
                "source_note_id": source_id,
                "original_end_ms": note["source_end_ms"],
                "proposed_end_ms": note["source_end_ms"] + 50,
                "confidence": 0.9 - index * 0.1,
                "reason": "f0_voicing_extension",
            }
        )
    project["raw_notes"] = deepcopy(notes)
    project["transcription_evidence"] = {
        "note_model": {
            "name": "GAME medium",
            "implementation": "test",
            "code_revision": "test",
            "parameters": {},
        },
        "boundary_suggestions": suggestions,
    }
    with SessionLocal() as session:
        record = session.get(ProjectRecord, project["project_id"])
        record.document = project
        session.commit()
    return deepcopy(project["raw_notes"])


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


def test_pitch_edit_updates_performance_without_superseding_boundary() -> None:
    project = create_project()
    raw_notes = add_boundary_evidence(project)
    original_timing = (
        project["performance_notes"][0]["source_start_ms"],
        project["performance_notes"][0]["source_end_ms"],
    )
    project["notes"][0]["pitch_midi"] += 2

    result = client.patch(
        f"/v1/projects/{project['project_id']}",
        json={"expected_revision": 1, "notes": project["notes"]},
    ).json()

    assert result["performance_notes"][0]["pitch_midi"] == project["notes"][0]["pitch_midi"]
    assert (
        result["performance_notes"][0]["source_start_ms"],
        result["performance_notes"][0]["source_end_ms"],
    ) == original_timing
    assert result["transcription_evidence"]["boundary_suggestions"][0]["review_status"] == "pending"
    assert result["raw_notes"] == raw_notes


def test_timing_edit_updates_performance_and_only_supersedes_related_boundary() -> None:
    project = create_project()
    raw_notes = add_boundary_evidence(project)
    project["notes"][0]["quantized_duration"] += 0.5

    result = client.patch(
        f"/v1/projects/{project['project_id']}",
        json={"expected_revision": 1, "notes": project["notes"]},
    ).json()

    assert result["performance_notes"][0]["source_end_ms"] == 750
    suggestions = result["transcription_evidence"]["boundary_suggestions"]
    assert suggestions[0]["review_status"] == "superseded"
    assert suggestions[0]["superseded_reason"] == "manual_timing_edit"
    assert suggestions[1]["review_status"] == "pending"
    assert result["raw_notes"] == raw_notes

    reset = client.post(
        f"/v1/projects/{project['project_id']}/boundary-suggestions/boundary-0",
        json={"expected_revision": result["revision"], "action": "reset"},
    )
    assert reset.status_code == 409
    assert reset.json()["detail"]["code"] == "SUGGESTION_SUPERSEDED"

    requantized = client.post(
        f"/v1/projects/{project['project_id']}/requantize",
        json={
            "expected_revision": result["revision"],
            "bpm": 120,
            "numerator": 4,
            "denominator": 4,
            "tonic": 0,
            "mode": "major",
            "grid": 0.25,
        },
    ).json()
    assert requantized["performance_notes"][0]["source_end_ms"] == 750
    assert requantized["notes"][0]["quantized_duration"] == 1.5


def test_delete_and_split_supersede_boundary_with_specific_reasons() -> None:
    deleted_project = create_project()
    add_boundary_evidence(deleted_project)
    deleted = client.patch(
        f"/v1/projects/{deleted_project['project_id']}",
        json={"expected_revision": 1, "notes": deleted_project["notes"][1:]},
    ).json()
    assert all(
        note["id"] != deleted_project["notes"][0]["id"]
        for note in deleted["performance_notes"]
    )
    deleted_suggestion = deleted["transcription_evidence"]["boundary_suggestions"][0]
    assert deleted_suggestion["review_status"] == "superseded"
    assert deleted_suggestion["superseded_reason"] == "target_deleted"

    split_project = create_project()
    add_boundary_evidence(split_project)
    original = split_project["notes"][0]
    half = original["quantized_duration"] / 2
    original["quantized_duration"] = half
    right = deepcopy(original)
    right["id"] = "manual-split-right"
    right["quantized_start"] += half
    split_project["notes"].insert(1, right)
    split = client.patch(
        f"/v1/projects/{split_project['project_id']}",
        json={"expected_revision": 1, "notes": split_project["notes"]},
    ).json()
    owners = [
        note
        for note in split["performance_notes"]
        if "source-0" in note["source_note_ids"]
    ]
    assert len(owners) == 2
    split_suggestion = split["transcription_evidence"]["boundary_suggestions"][0]
    assert split_suggestion["review_status"] == "superseded"
    assert split_suggestion["superseded_reason"] == "target_structure_changed"


def test_merge_preserves_source_union_and_supersedes_both_boundaries() -> None:
    project = create_project()
    raw_notes = add_boundary_evidence(project)
    left, right = project["notes"][:2]
    left["source_note_ids"] = ["source-0", "source-1"]
    left["quantized_duration"] = (
        right["quantized_start"] + right["quantized_duration"] - left["quantized_start"]
    )
    merged_notes = [left, *project["notes"][2:]]

    result = client.patch(
        f"/v1/projects/{project['project_id']}",
        json={"expected_revision": 1, "notes": merged_notes},
    ).json()

    assert result["performance_notes"][0]["source_note_ids"] == ["source-0", "source-1"]
    suggestions = result["transcription_evidence"]["boundary_suggestions"]
    assert [item["review_status"] for item in suggestions] == ["superseded", "superseded"]
    assert all(
        item["superseded_reason"] == "target_structure_changed" for item in suggestions
    )
    assert result["raw_notes"] == raw_notes


def test_project_catalog_can_rename_score_and_audio_project() -> None:
    project = create_project()
    catalog = client.get("/v1/project-catalog")
    assert catalog.status_code == 200
    item = next(row for row in catalog.json() if row["project_id"] == project["project_id"])
    assert item["project_name"] == "edit"
    assert item["score_name"] == "edit-1"

    renamed_score = client.patch(
        f"/v1/projects/{project['project_id']}/name",
        json={"expected_revision": project["revision"], "name": "GAME 试验"},
    )
    assert renamed_score.status_code == 200
    renamed_audio = client.patch(
        f"/v1/uploads/{item['upload_id']}/name",
        json={"expected_revision": 1, "name": "我的歌曲"},
    )
    assert renamed_audio.status_code == 200
    item = next(
        row
        for row in client.get("/v1/project-catalog").json()
        if row["project_id"] == project["project_id"]
    )
    assert item["project_name"] == "我的歌曲"
    assert item["score_name"] == "GAME 试验"


def test_generated_project_persists_upload_and_score_default_names() -> None:
    upload = client.post(
        "/v1/uploads",
        files={"file": ("named-song.wav", BytesIO(b"RIFF-named"), "audio/wav")},
    ).json()
    client.patch(
        f"/v1/uploads/{upload['id']}/name",
        json={"expected_revision": 1, "name": "我的默认项目"},
    )
    job = client.post("/v1/jobs", json={"upload_id": upload["id"]}).json()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = client.get(f"/v1/jobs/{job['id']}").json()
        if job["status"] == "completed":
            break
        time.sleep(0.03)
    project = client.get(f"/v1/projects/{job['project_id']}").json()
    assert project["project_group_id"] == upload["id"]
    assert project["project_name"] == "我的默认项目"
    assert project["score_name"] == "named-song-1"


def test_uploaded_audio_appears_in_catalog_before_score_generation() -> None:
    upload = client.post(
        "/v1/uploads",
        files={"file": ("new-song.wav", BytesIO(b"RIFF-new-audio"), "audio/wav")},
    ).json()

    item = next(
        row
        for row in client.get("/v1/project-catalog").json()
        if row["upload_id"] == upload["id"]
    )
    assert item["project_id"] is None
    assert item["project_name"] == "new-song"
    assert item["score_name"] is None
    assert item["note_count"] == 0


def test_bulk_delete_keeps_shared_upload_until_last_score() -> None:
    first = create_project()
    with SessionLocal() as session:
        first_record = session.get(ProjectRecord, first["project_id"])
        first_job = session.get(JobRecord, first_record.job_id)
        upload_id = first_job.upload_id
    second_job = client.post(
        "/v1/jobs", json={"upload_id": upload_id, "options": {"auto_start": False}}
    ).json()
    # The fake worker is deterministic, so run the job through its normal path.
    from app.job_runner import run_fake_job

    run_fake_job(second_job["id"])
    second_job = client.get(f"/v1/jobs/{second_job['id']}").json()
    second = client.get(f"/v1/projects/{second_job['project_id']}").json()
    assert second["score_name"] == "edit-2"

    response = client.post("/v1/projects/bulk-delete", json={"project_ids": [first["project_id"]]})
    assert response.status_code == 200
    assert response.json()["deleted_projects"] == 1
    assert client.get(f"/v1/projects/{second['project_id']}").status_code == 200
    response = client.post("/v1/projects/bulk-delete", json={"project_ids": [second["project_id"]]})
    assert response.status_code == 200
    assert client.get(f"/v1/projects/{second['project_id']}").status_code == 404


def test_project_can_be_requantized() -> None:
    project = create_project()
    performance_notes = project["performance_notes"]
    assert performance_notes
    performance_notes[1]["source_start_ms"] = performance_notes[0]["source_start_ms"]
    performance_notes[1]["source_end_ms"] = performance_notes[0]["source_end_ms"]
    with SessionLocal() as session:
        record = session.get(ProjectRecord, project["project_id"])
        record.document = project
        session.commit()
    project["notes"][0]["quantized_start"] = 9
    project["notes"][0]["quantized_duration"] = 9
    project["notes"][1]["quantized_start"] = 9
    project["notes"][1]["quantized_duration"] = 9
    patched = client.patch(
        f"/v1/projects/{project['project_id']}",
        json={"expected_revision": project["revision"], "notes": project["notes"]},
    ).json()
    assert patched["performance_notes"][0]["source_start_ms"] == 4500
    assert patched["performance_notes"][0]["source_end_ms"] == 9000
    assert patched["performance_notes"][1]["source_start_ms"] == 4500
    assert patched["performance_notes"][1]["source_end_ms"] == 9000
    performance_notes = patched["performance_notes"]
    response = client.post(
        f"/v1/projects/{project['project_id']}/requantize",
        json={
            "expected_revision": patched["revision"],
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
    assert result["revision"] == 3
    assert result["analysis"]["tempo_map"][0]["bpm"] == 90
    assert result["analysis"]["meter_map"][0]["numerator"] == 3
    assert result["analysis"]["key_map"][0]["tonic"] == 7
    assert result["pipeline"][-1]["stage"] == "requantize"
    assert result["pipeline"][-1]["version"] == "3"
    assert result["performance_notes"] == performance_notes
    assert result["notes"][0]["quantized_start"] != 9
    assert len(result["notes"]) == len(performance_notes)
    assert result["notes"][0]["quantized_start"] == result["notes"][1]["quantized_start"]
    assert len(result["quantization"]["conflicts"]) == 1

    repeated = client.post(
        f"/v1/projects/{project['project_id']}/requantize",
        json={
            "expected_revision": result["revision"],
            "bpm": 90,
            "numerator": 3,
            "denominator": 4,
            "tonic": 7,
            "mode": "minor",
            "grid": 0.5,
        },
    ).json()
    assert repeated["notes"] == result["notes"]
    assert repeated["performance_notes"] == performance_notes


def test_requantize_supports_disabled_partial_and_triplet_grids() -> None:
    project = create_project()
    note = project["performance_notes"][0]
    raw_start = note["source_start_ms"] / 500

    disabled = client.post(
        f"/v1/projects/{project['project_id']}/requantize",
        json={
            "expected_revision": project["revision"],
            "bpm": 120,
            "numerator": 4,
            "denominator": 4,
            "tonic": 0,
            "mode": "major",
            "enabled": False,
            "grid": 1 / 6,
            "strength": 1,
            "offset_ms": 0,
        },
    ).json()
    assert disabled["notes"][0]["quantized_start"] == raw_start
    assert disabled["quantization"]["enabled"] is False
    assert disabled["quantization"]["grid"] == 1 / 6

    partial = client.post(
        f"/v1/projects/{project['project_id']}/requantize",
        json={
            "expected_revision": disabled["revision"],
            "bpm": 120,
            "numerator": 4,
            "denominator": 4,
            "tonic": 0,
            "mode": "major",
            "enabled": True,
            "grid": 1 / 3,
            "strength": 0.5,
            "offset_ms": 40,
        },
    ).json()
    snapped = round((raw_start - 0.08) / (1 / 3)) * (1 / 3) + 0.08
    assert partial["notes"][0]["quantized_start"] == (raw_start + snapped) / 2
    assert partial["quantization"]["strength"] == 0.5
    assert partial["quantization"]["offset_ms"] == 40


def test_requantize_supports_piecewise_tempo_map() -> None:
    project = create_project()
    note = project["performance_notes"][1]
    note["source_start_ms"] = 1_250
    note["source_end_ms"] = 1_750
    with SessionLocal() as session:
        record = session.get(ProjectRecord, project["project_id"])
        record.document = project
        session.commit()

    response = client.post(
        f"/v1/projects/{project['project_id']}/requantize",
        json={
            "expected_revision": project["revision"],
            "bpm": 120,
            "numerator": 4,
            "denominator": 4,
            "tonic": 0,
            "mode": "major",
            "grid": 0.25,
            "tempo_map": [
                {"time_ms": 1_000, "bpm": 60},
                {"time_ms": 0, "bpm": 120},
            ],
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["analysis"]["tempo_map"] == [
        {"time_ms": 0, "bpm": 120},
        {"time_ms": 1_000, "bpm": 60},
    ]
    # 1.25 s = 2 beats at 120 BPM plus 0.25 beats at 60 BPM.
    assert result["notes"][1]["quantized_start"] == 2.25


def test_project_exports_standard_midi_and_musicxml(monkeypatch) -> None:
    project = create_project()
    project_id = project["project_id"]

    midi = client.get(f"/v1/projects/{project_id}/exports/midi")
    assert midi.status_code == 200
    assert midi.content.startswith(b"MThd")
    assert b"MTrk" in midi.content
    assert midi.headers["content-disposition"].endswith(f'"{project_id}.mid"')

    performance_midi = client.get(f"/v1/projects/{project_id}/exports/midi?version=performance")
    assert performance_midi.status_code == 200
    assert performance_midi.content.startswith(b"MThd")
    assert performance_midi.headers["content-disposition"].endswith(
        f'"{project_id}.performance.mid"'
    )
    assert client.get(f"/v1/projects/{project_id}/exports/midi?version=unknown").status_code == 422

    musicxml = client.get(f"/v1/projects/{project_id}/exports/musicxml")
    assert musicxml.status_code == 200
    assert b'<score-partwise version="4.0">' in musicxml.content
    assert b"<work-title>edit-1</work-title>" in musicxml.content
    assert musicxml.content.count(b"<note") >= len(project["notes"])
    assert musicxml.content.count(b"<measure ") == 3

    def fake_convert(svg: bytes, output_format: str, renderer_url: str | None) -> bytes:
        assert svg.startswith(b"<svg")
        assert output_format in {"png", "pdf"}
        return b"PNG" if output_format == "png" else b"%PDF-1.4"

    def fake_engrave(
        musicxml: bytes, output_format: str, renderer_url: str | None
    ) -> bytes:
        assert b"<score-partwise" in musicxml
        assert output_format in {"png", "pdf"}
        return b"PNG" if output_format == "png" else b"%PDF-1.4"

    monkeypatch.setattr("app.routes.convert_svg", fake_convert)
    monkeypatch.setattr("app.routes.engrave_musicxml", fake_engrave)
    revision_before = client.get(f"/v1/projects/{project_id}").json()["revision"]
    staff_png = client.get(f"/v1/projects/{project_id}/exports/staff.png")
    jianpu_pdf = client.get(f"/v1/projects/{project_id}/exports/jianpu.pdf")
    assert staff_png.status_code == 200 and staff_png.content == b"PNG"
    assert staff_png.headers["content-type"].startswith("image/png")
    assert staff_png.headers["x-score-renderer"] == "verovio+inkscape"
    assert staff_png.headers["x-score-format"] == "staff.png"
    assert jianpu_pdf.status_code == 200 and jianpu_pdf.content.startswith(b"%PDF")
    assert jianpu_pdf.headers["content-type"].startswith("application/pdf")
    assert jianpu_pdf.headers["x-score-renderer"] == "native-jianpu+inkscape"
    assert client.get(f"/v1/projects/{project_id}").json()["revision"] == revision_before

    audio = client.get(f"/v1/projects/{project_id}/audio")
    assert audio.status_code == 200
    assert audio.content == b"RIFF-edit-audio"
    assert audio.headers["content-type"].startswith("audio/wav")


def test_project_streams_separate_f0_evidence() -> None:
    project = create_project()
    project_id = project["project_id"]
    object_key = f"work/{project_id}/evidence/f0.jsonl"
    content = (
        b'{"time_seconds":0.0,"f0_hz":440.0,"periodicity":0.9}\n'
        b'{"time_seconds":0.01,"f0_hz":441.0,"periodicity":0.8}\n'
    )
    target = get_settings().data_dir / object_key
    target.parent.mkdir(parents=True)
    target.write_bytes(content)
    project["transcription_evidence"] = {
        "note_model": {
            "name": "GAME medium",
            "implementation": "test",
            "code_revision": "test",
        },
        "f0_track": {
            "object_key": object_key,
            "format": "jsonl",
            "frame_period_ms": 10,
            "frame_count": 2,
            "voiced_frame_count": 2,
            "duration_ms": 20,
            "provenance": {
                "name": "torchcrepe full",
                "implementation": "test",
                "code_revision": "test",
            },
        },
    }
    with SessionLocal() as session:
        record = session.get(ProjectRecord, project_id)
        record.document = project
        session.commit()

    response = client.get(f"/v1/projects/{project_id}/evidence/f0")
    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"].startswith("application/x-ndjson")


def test_project_f0_evidence_is_optional() -> None:
    project = create_project()
    response = client.get(f"/v1/projects/{project['project_id']}/evidence/f0")
    assert response.status_code == 404


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


def test_transcription_evidence_is_optional_and_round_trips() -> None:
    legacy = create_project()
    assert "transcription_evidence" in legacy
    assert legacy["transcription_evidence"] is None

    legacy.pop("transcription_evidence")
    legacy.pop("performance_notes")
    parsed = ScoreProject.model_validate(legacy)
    assert parsed.transcription_evidence is None
    assert parsed.performance_notes is not None
    assert parsed.performance_notes[0].source_start_ms == parsed.notes[0].source_start_ms

    legacy["transcription_evidence"] = {
        "note_model": {
            "name": "GAME medium",
            "implementation": "game_subprocess",
            "code_revision": "0123456789abcdef",
            "model_revision": "medium-2024-07-17",
            "weight_sha256": "a" * 64,
            "parameters": {"presence_threshold": 0.15, "boundary_threshold": 0.10},
            "device": "cpu",
        },
        "f0_track": {
            "object_key": "work/job-1/evidence/f0.jsonl",
            "format": "jsonl",
            "frame_period_ms": 10,
            "frame_count": 101,
            "voiced_frame_count": 88,
            "duration_ms": 1000,
            "provenance": {
                "name": "torchcrepe full",
                "implementation": "torchcrepe_subprocess",
                "code_revision": "19e2ec3d494c0797a5ff2a11408ec5838fba6681",
                "model_revision": "0.0.24",
                "weight_sha256": "b" * 64,
                "parameters": {"periodicity_threshold": 0.4},
                "device": "cpu",
            },
        },
        "boundary_suggestions": [
            {
                "id": "suggestion-1",
                "source_note_id": legacy["notes"][0]["id"],
                "kind": "adjust_end",
                "original_end_ms": 450,
                "proposed_end_ms": 520,
                "confidence": 0.83,
                "reason": "f0_voicing_extension",
                "review_status": "pending",
            }
        ],
    }
    evidence = ScoreProject.model_validate(legacy).model_dump(mode="json")["transcription_evidence"]
    assert evidence is not None
    assert evidence["f0_track"]["frame_count"] == 101
    assert evidence["boundary_suggestions"][0]["review_status"] == "pending"


def test_boundary_suggestion_review_accept_reject_and_reset() -> None:
    project = create_project()
    project_id = project["project_id"]
    original_end = project["notes"][0]["source_end_ms"]
    original_duration = project["notes"][0]["quantized_duration"]
    proposed_end = original_end + 230
    project["notes"][0]["source_note_ids"] = ["game-0000"]
    project["performance_notes"][0]["source_note_ids"] = ["game-0000"]
    project["raw_notes"] = [dict(note) for note in project["notes"]]
    project["transcription_evidence"] = {
        "note_model": {
            "name": "GAME medium",
            "implementation": "test",
            "code_revision": "test",
            "parameters": {},
        },
        "boundary_suggestions": [
            {
                "id": "boundary-1",
                "source_note_id": "game-0000",
                "original_end_ms": original_end,
                "proposed_end_ms": proposed_end,
                "confidence": 0.8,
                "reason": "f0_voicing_extension",
            }
        ],
    }
    with SessionLocal() as session:
        record = session.get(ProjectRecord, project_id)
        record.document = project
        session.commit()

    path = f"/v1/projects/{project_id}/boundary-suggestions/boundary-1"
    accepted = client.post(path, json={"expected_revision": 1, "action": "accept"})
    assert accepted.status_code == 200
    accepted_project = accepted.json()
    assert accepted_project["revision"] == 2
    assert accepted_project["notes"][0]["source_end_ms"] == proposed_end
    assert accepted_project["notes"][0]["quantized_duration"] == 1.25
    assert accepted_project["raw_notes"][0]["source_end_ms"] == original_end
    assert (
        accepted_project["transcription_evidence"]["boundary_suggestions"][0]["review_status"]
        == "accepted"
    )
    assert client.post(path, json={"expected_revision": 1, "action": "reset"}).status_code == 409

    reset = client.post(path, json={"expected_revision": 2, "action": "reset"})
    assert reset.status_code == 200
    assert reset.json()["notes"][0]["source_end_ms"] == original_end
    assert reset.json()["notes"][0]["quantized_duration"] == original_duration
    assert reset.json()["notes"][0]["origin"] == "model"
    assert reset.json()["performance_notes"][0]["source_end_ms"] == original_end
    assert (
        reset.json()["transcription_evidence"]["boundary_suggestions"][0]["review_status"]
        == "pending"
    )

    rejected = client.post(path, json={"expected_revision": 3, "action": "reject"})
    assert rejected.status_code == 200
    assert rejected.json()["revision"] == 4
    assert rejected.json()["notes"][0]["source_end_ms"] == original_end
    reset_rejection = client.post(path, json={"expected_revision": 4, "action": "reset"})
    assert reset_rejection.status_code == 200
    assert (
        reset_rejection.json()["transcription_evidence"]["boundary_suggestions"][0]["review_status"]
        == "pending"
    )


def test_boundary_suggestion_batch_route_accepts_and_resets() -> None:
    project = create_project()
    project_id = project["project_id"]
    original_end = project["notes"][0]["source_end_ms"]
    proposed_end = original_end + 70
    project["notes"][0]["source_note_ids"] = ["game-0000"]
    project["performance_notes"][0]["source_note_ids"] = ["game-0000"]
    project["transcription_evidence"] = {
        "note_model": {
            "name": "GAME medium",
            "implementation": "test",
            "code_revision": "test",
            "parameters": {},
        },
        "boundary_suggestions": [
            {
                "id": "boundary-batch-1",
                "source_note_id": "game-0000",
                "original_end_ms": original_end,
                "proposed_end_ms": proposed_end,
                "confidence": 0.9,
                "reason": "f0_voicing_extension",
            }
        ],
    }
    with SessionLocal() as session:
        record = session.get(ProjectRecord, project_id)
        record.document = project
        session.commit()

    path = f"/v1/projects/{project_id}/boundary-suggestions/batch"
    accepted = client.post(
        path,
        json={"expected_revision": 1, "threshold": 0.85, "action": "accept"},
    )
    assert accepted.status_code == 200
    accepted_project = accepted.json()
    assert accepted_project["notes"][0]["source_end_ms"] == proposed_end
    assert accepted_project["notes"][0]["quantized_duration"] == 1.0
    assert (
        accepted_project["transcription_evidence"]["boundary_suggestions"][0]["review_status"]
        == "accepted"
    )
    assert accepted_project["transcription_evidence"]["last_boundary_batch_id"]

    reset = client.post(
        path,
        json={"expected_revision": 2, "threshold": 0, "action": "reset"},
    )
    assert reset.status_code == 200
    reset_project = reset.json()
    assert reset_project["notes"][0]["source_end_ms"] == original_end
    assert (
        reset_project["transcription_evidence"]["boundary_suggestions"][0]["review_status"]
        == "pending"
    )


def test_boundary_suggestion_accept_refuses_changed_target() -> None:
    project = create_project()
    project["notes"][0]["source_note_ids"] = ["game-0000"]
    project["performance_notes"][0]["source_note_ids"] = ["game-0000"]
    project["transcription_evidence"] = {
        "note_model": {
            "name": "GAME medium",
            "implementation": "test",
            "code_revision": "test",
            "parameters": {},
        },
        "boundary_suggestions": [
            {
                "id": "boundary-1",
                "source_note_id": "game-0000",
                "original_end_ms": project["notes"][0]["source_end_ms"] - 20,
                "proposed_end_ms": project["notes"][0]["source_end_ms"] + 20,
                "confidence": 0.7,
                "reason": "f0_voicing_extension",
            }
        ],
    }
    with SessionLocal() as session:
        record = session.get(ProjectRecord, project["project_id"])
        record.document = project
        session.commit()
    response = client.post(
        f"/v1/projects/{project['project_id']}/boundary-suggestions/boundary-1",
        json={"expected_revision": 1, "action": "accept"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SUGGESTION_TARGET_CHANGED"


def test_boundary_suggestion_reset_preserves_later_duration_edit() -> None:
    project = create_project()
    project["notes"][0]["source_note_ids"] = ["game-0000"]
    project["performance_notes"][0]["source_note_ids"] = ["game-0000"]
    original_end = project["notes"][0]["source_end_ms"]
    project["transcription_evidence"] = {
        "note_model": {
            "name": "GAME medium",
            "implementation": "test",
            "code_revision": "test",
        },
        "boundary_suggestions": [
            {
                "id": "boundary-1",
                "source_note_id": "game-0000",
                "original_end_ms": original_end,
                "proposed_end_ms": original_end + 70,
                "confidence": 0.7,
                "reason": "f0_voicing_extension",
            }
        ],
    }
    with SessionLocal() as session:
        record = session.get(ProjectRecord, project["project_id"])
        record.document = project
        session.commit()
    path = f"/v1/projects/{project['project_id']}/boundary-suggestions/boundary-1"
    accepted = client.post(path, json={"expected_revision": 1, "action": "accept"}).json()
    accepted["notes"][0]["quantized_duration"] += 0.25
    patched = client.patch(
        f"/v1/projects/{project['project_id']}",
        json={"expected_revision": 2, "notes": accepted["notes"]},
    )
    assert patched.status_code == 200
    reset = client.post(path, json={"expected_revision": 3, "action": "reset"})
    assert reset.status_code == 409
    assert reset.json()["detail"]["code"] == "SUGGESTION_SUPERSEDED"
