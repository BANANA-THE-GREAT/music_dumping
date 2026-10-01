import csv
import hashlib
import json
import math
import os
import wave
from dataclasses import asdict
from pathlib import Path
from typing import Any

from vss_worker.adapters import DetectedNote
from vss_worker.evaluation import evaluate_transcription

VOCADITO_MD5 = "dea40fd18f14d899643c4ba221b33a46"
VOCADITO_SHA256 = "e0d6b99d3f9c594afe5ae5c4d7bdacebe569e53b809e90b89d1c771c4f9990e3"
HOLDOUT_SINGERS = {"S1", "S6", "S9", "S21", "S28", "S29"}
PREDICTION_VARIANTS = (
    "basic_pitch_raw",
    "basic_pitch_refined",
    "basic_pitch_quantized",
    "game_1_0_small",
    "game_1_0_medium",
    "some_continuous256_5spk",
)


def file_hash(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hz_to_midi(hz: float) -> float:
    if hz <= 0:
        raise ValueError("note frequency must be positive")
    return 69 + 12 * math.log2(hz / 440)


def read_note_annotation(path: Path, source_prefix: str) -> list[DetectedNote]:
    notes = []
    with path.open(encoding="utf-8", newline="") as source:
        for index, row in enumerate(csv.reader(source)):
            start, hz, duration = (float(value) for value in row)
            midi = hz_to_midi(hz)
            notes.append(
                DetectedNote(
                    start_seconds=start,
                    end_seconds=start + duration,
                    pitch_midi=round(midi),
                    confidence=1.0,
                    source_id=f"{source_prefix}-{index:04d}",
                    pitch_cents=midi * 100,
                )
            )
    return notes


def _write_notes(path: Path, notes: list[DetectedNote]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"notes": [asdict(note) for note in notes]}, indent=2) + "\n",
        encoding="utf-8",
    )


def _duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def _relative(target: Path, manifest_path: Path) -> str:
    return Path(os.path.relpath(target, manifest_path.parent)).as_posix()


def _uncertain_regions(
    primary: list[DetectedNote], alternate: list[DetectedNote]
) -> list[dict[str, object]]:
    matched_alternate: set[int] = set()
    regions: list[tuple[float, float, str]] = []
    for note in primary:
        note_cents = note.pitch_cents or note.pitch_midi * 100
        candidates = [
            index
            for index, other in enumerate(alternate)
            if index not in matched_alternate
            and abs(note_cents - (other.pitch_cents or other.pitch_midi * 100)) <= 50
            and abs(note.start_seconds - other.start_seconds) <= 0.05
            and abs(note.end_seconds - other.end_seconds)
            <= max(0.05, (note.end_seconds - note.start_seconds) * 0.2)
        ]
        if candidates:
            matched_alternate.add(
                min(
                    candidates,
                    key=lambda index: abs(
                        note.start_seconds - alternate[index].start_seconds
                    ),
                )
            )
        else:
            regions.append(
                (
                    note.start_seconds,
                    note.end_seconds,
                    "primary_only_or_boundary_disagreement",
                )
            )
    regions.extend(
        (note.start_seconds, note.end_seconds, "alternate_only_or_boundary_disagreement")
        for index, note in enumerate(alternate)
        if index not in matched_alternate
    )
    return [
        {"start_seconds": start, "end_seconds": end, "reason": reason}
        for start, end, reason in sorted(regions)
    ]


def prepare_vocadito(
    dataset_root: Path,
    output_root: Path,
    manifest_path: Path,
    *,
    prediction_root: Path | None = None,
) -> dict[str, Any]:
    archive = dataset_root / "vocadito.zip"
    if archive.is_file():
        if file_hash(archive, "md5") != VOCADITO_MD5:
            raise ValueError("Vocadito archive MD5 does not match the published checksum")
        if file_hash(archive, "sha256") != VOCADITO_SHA256:
            raise ValueError("Vocadito archive SHA-256 does not match the recorded checksum")

    metadata_path = dataset_root / "vocadito_metadata.csv"
    with metadata_path.open(encoding="utf-8", newline="") as source:
        metadata = list(csv.DictReader(source))
    if len(metadata) != 40:
        raise ValueError(f"Expected 40 Vocadito tracks, found {len(metadata)}")

    clips: list[dict[str, object]] = []
    agreement = []
    singers_by_split: dict[str, set[str]] = {"tuning": set(), "holdout": set()}
    for item in metadata:
        track_id = item["track_id"]
        singer_id = item["singer_id"]
        split = "holdout" if singer_id in HOLDOUT_SINGERS else "tuning"
        singers_by_split[split].add(singer_id)
        stem = f"vocadito_{track_id}"
        audio = dataset_root / "Audio" / f"{stem}.wav"
        if not audio.is_file():
            raise FileNotFoundError(audio)
        references: dict[str, Path] = {}
        annotations: dict[str, list[DetectedNote]] = {}
        for annotator in ("A1", "A2"):
            annotation_path = (
                dataset_root / "Annotations" / "Notes" / f"{stem}_notes{annotator}.csv"
            )
            notes = read_note_annotation(annotation_path, f"{stem}-{annotator.lower()}")
            reference_path = output_root / "references" / annotator.lower() / f"{stem}.json"
            _write_notes(reference_path, notes)
            references[annotator] = reference_path
            annotations[annotator] = notes
        agreement.append(
            {
                "id": stem,
                "split": split,
                "singer_id": singer_id,
                "a1_note_count": len(annotations["A1"]),
                "a2_note_count": len(annotations["A2"]),
                "uncertain_regions": _uncertain_regions(
                    annotations["A1"], annotations["A2"]
                ),
                "metrics": asdict(
                    evaluate_transcription(annotations["A1"], annotations["A2"])
                ),
            }
        )
        predictions = {}
        if prediction_root is not None:
            for variant in PREDICTION_VARIANTS:
                candidate = prediction_root / variant / f"{stem}.json"
                if candidate.is_file():
                    predictions[variant] = _relative(candidate, manifest_path)
        clips.append(
            {
                "id": stem,
                "split": split,
                "tags": [
                    "vocadito",
                    f"language:{item['language']}",
                    f"singer:{singer_id}",
                ],
                "audio": _relative(audio, manifest_path),
                "audio_license": "CC BY 4.0",
                "duration_seconds": round(_duration_seconds(audio), 6),
                "reference": _relative(references["A1"], manifest_path),
                "alternate_reference": _relative(references["A2"], manifest_path),
                "predictions": predictions,
            }
        )

    leaked_singers = singers_by_split["tuning"] & singers_by_split["holdout"]
    if leaked_singers:
        raise ValueError(f"Singer leakage detected: {sorted(leaked_singers)}")
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "annotation-agreement.json").write_text(
        json.dumps({"schema_version": "1.0", "clips": agreement}, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "dataset_status": "authorized_real_vocals",
        "description": "Vocadito isolated-vocal P0 baseline with singer-disjoint splits.",
        "dataset": {
            "name": "Vocadito",
            "official_url": "https://zenodo.org/records/5578807",
            "doi": "10.5281/zenodo.5578807",
            "authors": [
                "Rachel Bittner",
                "Katherine Pasalo",
                "Juan José Bosch",
                "Gabriel Meseguer Brocal",
                "David Rubinstein",
            ],
            "license": "CC BY 4.0",
            "attribution": (
                "Vocadito by Rachel Bittner, Katherine Pasalo, Juan José Bosch, "
                "Gabriel Meseguer Brocal, and David Rubinstein; licensed under "
                "CC BY 4.0. DOI: 10.5281/zenodo.5578807."
            ),
            "archive_md5": VOCADITO_MD5,
            "archive_sha256": VOCADITO_SHA256,
            "primary_reference": "annotator A1",
            "alternate_reference": "annotator A2",
        },
        "split_policy": {
            "unit": "singer_id",
            "holdout_singers": sorted(HOLDOUT_SINGERS),
            "tuning_singers": sorted(singers_by_split["tuning"]),
        },
        "tolerances": {
            "pitch_cents": 50,
            "onset_ms": 50,
            "minimum_offset_ms": 50,
            "offset_duration_ratio": 0.2,
        },
        "quality_gate": {
            "status": "preregistered_before_candidate_model_evaluation",
            "candidate_onset_offset_f1_improvement": 0.03,
            "candidate_recall_improvement": 0.05,
            "maximum_precision_regression": 0.02,
            "maximum_failure_rate": 0.02,
        },
        "clips": clips,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
