import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from vss_worker.experimental import (
    ExperimentalEngineConfigurationError,
    GameF0EvidenceTranscriber,
)


def _runtime(tmp_path: Path) -> tuple[Path, Path, Path]:
    model = tmp_path / "models" / "model.pt"
    model.parent.mkdir()
    model.write_bytes(b"test-game-weight")
    game_root = tmp_path / "game"
    (game_root / "inference").mkdir(parents=True)
    torchcrepe_root = tmp_path / "torchcrepe-root"
    (torchcrepe_root / "torchcrepe").mkdir(parents=True)
    return model, game_root, torchcrepe_root


def test_experimental_transcriber_rejects_missing_weight(tmp_path: Path) -> None:
    transcriber = GameF0EvidenceTranscriber(
        model_path=tmp_path / "missing.pt",
        game_root=tmp_path / "game",
        torchcrepe_root=tmp_path / "torchcrepe",
    )
    with pytest.raises(ExperimentalEngineConfigurationError, match="weight is missing"):
        transcriber.validate_runtime()


def test_experimental_transcriber_preserves_notes_and_emits_suggestions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model, game_root, torchcrepe_root = _runtime(tmp_path)
    monkeypatch.setattr(
        "vss_worker.experimental.GAME_MODEL_SHA256", hashlib.sha256(model.read_bytes()).hexdigest()
    )

    def fake_command(arguments: Sequence[str]) -> None:
        target = Path(arguments[4])
        if arguments[2] == "vss_worker.game_cli":
            target.write_text(
                json.dumps(
                    {
                        "notes": [
                            {
                                "start_seconds": 0.1,
                                "end_seconds": 0.5,
                                "pitch_midi": 60,
                                "confidence": 1.0,
                                "source_id": "game-0000",
                                "pitch_cents": 6000.0,
                            }
                        ],
                        "segmentation": {
                            "method": "silence",
                            "overlap_ms": 0,
                            "segments": [
                                {"offset_seconds": 0.0, "duration_seconds": 0.81}
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )
            return
        frames = []
        for index in range(81):
            time_seconds = index / 100
            frames.append(
                json.dumps(
                    {
                        "time_seconds": time_seconds,
                        "f0_hz": 261.625565,
                        "periodicity": 0.9 if time_seconds <= 0.69 else 0.1,
                    }
                )
            )
        target.write_text("\n".join(frames) + "\n", encoding="utf-8")

    vocal = tmp_path / "vocal.wav"
    vocal.write_bytes(b"audio")
    evidence_dir = tmp_path / "work" / "job-1" / "evidence"
    result = GameF0EvidenceTranscriber(
        model_path=model,
        game_root=game_root,
        torchcrepe_root=torchcrepe_root,
        command_runner=fake_command,
    ).transcribe(vocal, evidence_dir)

    assert result.notes[0].end_seconds == 0.5
    evidence = result.transcription_evidence
    assert evidence["note_model"]["parameters"]["segmentation"]["overlap_ms"] == 0
    assert evidence["f0_track"]["object_key"] == "work/job-1/evidence/f0.jsonl"
    suggestions = evidence["boundary_suggestions"]
    assert suggestions == [
        {
            "id": "boundary-game-0000-500-700",
            "source_note_id": "game-0000",
            "kind": "adjust_end",
            "original_end_ms": 500,
            "proposed_end_ms": 700,
            "confidence": 0.9,
            "reason": "f0_voicing_extension",
            "review_status": "pending",
        }
    ]
