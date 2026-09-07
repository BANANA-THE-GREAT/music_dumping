import hashlib
import json
import math
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from vss_worker.adapters import DetectedNote, EvidenceTranscription
from vss_worker.command import run_command
from vss_worker.device import resolve_inference_device
from vss_worker.f0_diagnostics import adjust_note_offsets

GAME_COMMIT = "e66c31251605e334b1bf0f565252d4987a9065c0"
GAME_MODEL_SHA256 = "e9904159fb0646e1a352b9d2bc74615547cfa3e32d45c7464d440ac142846d93"
TORCHCREPE_COMMIT = "19e2ec3d494c0797a5ff2a11408ec5838fba6681"
TORCHCREPE_MODEL_SHA256 = "133225604dedd2e4005f8bbd1bd0a2ec073ba8b7a6cd31ff6d5edbbfa3539986"

GAME_PARAMETERS: dict[str, object] = {
    "presence_threshold": 0.15,
    "boundary_threshold": 0.10,
    "d3pm_steps": 8,
    "language_id": 0,
    "batch_size": 4,
    "seed": 114514,
}
F0_HOP_MS = 10.0
F0_PARAMETERS: dict[str, object] = {
    "model": "full",
    "hop_ms": F0_HOP_MS,
    "fmin_hz": 50,
    "fmax_hz": 1100,
    "decoder": "viterbi",
    "periodicity_median_frames": 3,
    "silence_threshold_db": -60,
    "batch_size": 512,
}
BOUNDARY_PARAMETERS: dict[str, float] = {
    "periodicity_threshold": 0.40,
    "pitch_tolerance_cents": 100.0,
    "maximum_gap_ms": 20.0,
    "maximum_contraction_ms": 400.0,
    "maximum_extension_ms": 400.0,
    "minimum_overlap_ms": 30.0,
}


class ExperimentalEngineConfigurationError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_notes(
    path: Path,
) -> tuple[list[DetectedNote], dict[str, object] | None, str | None]:
    document = json.loads(path.read_text(encoding="utf-8"))
    notes = [DetectedNote(**note) for note in document["notes"]]
    segmentation = document.get("segmentation")
    device = document.get("device")
    return (
        notes,
        segmentation if isinstance(segmentation, dict) else None,
        device if isinstance(device, str) else None,
    )


def _read_f0_jsonl(path: Path) -> dict[str, list[float]]:
    prediction: dict[str, list[float]] = {
        "times_seconds": [],
        "f0_hz": [],
        "periodicity": [],
    }
    with path.open(encoding="utf-8") as source:
        for line in source:
            frame = json.loads(line)
            prediction["times_seconds"].append(float(frame["time_seconds"]))
            prediction["f0_hz"].append(float(frame["f0_hz"]))
            prediction["periodicity"].append(float(frame["periodicity"]))
    return prediction


def _pitch_support_confidence(
    note: DetectedNote, prediction: dict[str, list[float]], proposed_end: float
) -> float:
    expected_hz = 440 * 2 ** ((note.pitch_midi - 69) / 12)
    left, right = sorted((note.end_seconds, proposed_end))
    values = [
        periodicity
        for time_value, predicted_hz, periodicity in zip(
            prediction["times_seconds"],
            prediction["f0_hz"],
            prediction["periodicity"],
            strict=True,
        )
        if left - 0.03 <= time_value <= right + 0.03
        and predicted_hz > 0
        and abs(1200 * math.log2(predicted_hz / expected_hz))
        <= BOUNDARY_PARAMETERS["pitch_tolerance_cents"]
    ]
    return round(min(1.0, max(values, default=BOUNDARY_PARAMETERS["periodicity_threshold"])), 4)


class GameF0EvidenceTranscriber:
    def __init__(
        self,
        *,
        model_path: Path,
        game_root: Path,
        torchcrepe_root: Path,
        command_runner: Callable[[Sequence[str]], None] = run_command,
        device: str | None = None,
    ) -> None:
        self.model_path = model_path
        self.game_root = game_root
        self.torchcrepe_root = torchcrepe_root
        self.command_runner = command_runner
        self.device = resolve_inference_device(device)

    def validate_runtime(self) -> None:
        if not self.model_path.is_file():
            raise ExperimentalEngineConfigurationError(
                f"GAME medium weight is missing: {self.model_path}"
            )
        actual_hash = _sha256(self.model_path)
        if actual_hash != GAME_MODEL_SHA256:
            raise ExperimentalEngineConfigurationError(
                "GAME medium weight SHA-256 mismatch: "
                f"expected {GAME_MODEL_SHA256}, got {actual_hash}"
            )
        if not (self.game_root / "inference").is_dir():
            raise ExperimentalEngineConfigurationError(
                f"GAME runtime is missing: {self.game_root}"
            )
        if not (self.torchcrepe_root / "torchcrepe").is_dir():
            raise ExperimentalEngineConfigurationError(
                f"torchcrepe runtime is missing: {self.torchcrepe_root}"
            )

    def transcribe(self, vocal_path: Path, evidence_dir: Path) -> EvidenceTranscription:
        self.validate_runtime()
        evidence_dir.mkdir(parents=True, exist_ok=True)
        notes_path = evidence_dir / "game-notes.json"
        f0_path = evidence_dir / "f0.jsonl"
        started = time.perf_counter()
        self.command_runner(
            [
                sys.executable,
                "-m",
                "vss_worker.game_cli",
                str(vocal_path),
                str(notes_path),
                str(self.model_path),
                str(self.game_root),
                self.device,
            ]
        )
        game_elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        started = time.perf_counter()
        self.command_runner(
            [
                sys.executable,
                "-m",
                "vss_worker.torchcrepe_cli",
                str(vocal_path),
                str(f0_path),
                self.device,
            ]
        )
        f0_elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        notes, segmentation, game_device = _read_notes(notes_path)
        prediction = _read_f0_jsonl(f0_path)
        adjusted = adjust_note_offsets(notes, prediction, **BOUNDARY_PARAMETERS)
        suggestions: list[dict[str, object]] = []
        for note, revised in zip(notes, adjusted, strict=True):
            if math.isclose(note.end_seconds, revised.end_seconds, abs_tol=0.0005):
                continue
            original_end_ms = round(note.end_seconds * 1000)
            proposed_end_ms = round(revised.end_seconds * 1000)
            if original_end_ms == proposed_end_ms:
                continue
            source_id = note.source_id or f"game-{len(suggestions):04d}"
            suggestions.append(
                {
                    "id": f"boundary-{source_id}-{original_end_ms}-{proposed_end_ms}",
                    "source_note_id": source_id,
                    "kind": "adjust_end",
                    "original_end_ms": original_end_ms,
                    "proposed_end_ms": proposed_end_ms,
                    "confidence": _pitch_support_confidence(
                        note, prediction, revised.end_seconds
                    ),
                    "reason": (
                        "f0_voicing_extension"
                        if proposed_end_ms > original_end_ms
                        else "f0_voicing_contraction"
                    ),
                    "review_status": "pending",
                }
            )
        frame_count = len(prediction["times_seconds"])
        voiced_frame_count = sum(
            value >= BOUNDARY_PARAMETERS["periodicity_threshold"]
            for value in prediction["periodicity"]
        )
        duration_ms = (
            round(prediction["times_seconds"][-1] * 1000 + F0_HOP_MS)
            if frame_count
            else 0
        )
        object_key = f"work/{evidence_dir.parent.name}/evidence/{f0_path.name}"
        return EvidenceTranscription(
            notes=notes,
            transcription_evidence={
                "note_model": {
                    "name": "GAME medium",
                    "implementation": type(self).__name__,
                    "code_revision": GAME_COMMIT,
                    "model_revision": "1.0.0-medium",
                    "weight_sha256": GAME_MODEL_SHA256,
                    "parameters": {
                        **GAME_PARAMETERS,
                        "elapsed_ms": game_elapsed_ms,
                        **({"segmentation": segmentation} if segmentation else {}),
                    },
                    "device": game_device or self.device,
                },
                "f0_track": {
                    "object_key": object_key,
                    "format": "jsonl",
                    "frame_period_ms": F0_HOP_MS,
                    "frame_count": frame_count,
                    "voiced_frame_count": voiced_frame_count,
                    "duration_ms": duration_ms,
                    "provenance": {
                        "name": "torchcrepe full",
                        "implementation": "torchcrepe_cli",
                        "code_revision": TORCHCREPE_COMMIT,
                        "model_revision": "0.0.24",
                        "weight_sha256": TORCHCREPE_MODEL_SHA256,
                        "parameters": {
                            **F0_PARAMETERS,
                            **BOUNDARY_PARAMETERS,
                            "elapsed_ms": f0_elapsed_ms,
                        },
                        "device": self.device,
                    },
                },
                "boundary_suggestions": suggestions,
            },
        )
