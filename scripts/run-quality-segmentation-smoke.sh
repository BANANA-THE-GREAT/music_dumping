#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
image=vocal-score-studio-worker:latest
source_audio="$root/data/evaluation/vocadito/Audio/vocadito_20.wav"
model_root="$root/data/models/game"
output=${1:-"$root/evaluation/reports/game-segmentation-smoke.json"}
work=$(mktemp -d /tmp/vss-game-segments.XXXXXX)
trap 'rm -rf "$work"' EXIT

test -f "$source_audio"
test -f "$model_root/GAME-1.0-medium/model.pt"
docker image inspect "$image" >/dev/null

docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$(dirname "$source_audio"):/audio:ro" -v "$work:/output" \
  "$image" ffmpeg -hide_banner -loglevel error \
  -i "/audio/$(basename "$source_audio")" \
  -f lavfi -i anullsrc=r=44100:cl=mono:d=2 \
  -i "/audio/$(basename "$source_audio")" \
  -filter_complex '[0:a][1:a][2:a]concat=n=3:v=0:a=1[out]' \
  -map '[out]' /output/repeated.wav

docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$work:/input" -v "$model_root:/models/game:ro" \
  "$image" python -m vss_worker.game_cli \
  /input/repeated.wav /input/game-notes.json \
  /models/game/GAME-1.0-medium/model.pt /opt/game

source_duration=$(docker run --rm -v "$(dirname "$source_audio"):/audio:ro" \
  "$image" ffprobe -v error -show_entries format=duration \
  -of default=nw=1:nk=1 "/audio/$(basename "$source_audio")")
synthetic_duration=$(docker run --rm -v "$work:/input:ro" \
  "$image" ffprobe -v error -show_entries format=duration \
  -of default=nw=1:nk=1 /input/repeated.wav)
image_id=$(docker image inspect "$image" --format '{{.Id}}')

mkdir -p "$(dirname "$output")"
WORK="$work" OUTPUT="$output" SOURCE_DURATION="$source_duration" \
  SYNTHETIC_DURATION="$synthetic_duration" IMAGE_ID="$image_id" \
  "$root/.venv/bin/python" - <<'PY'
import json
import os
from pathlib import Path

document = json.loads((Path(os.environ["WORK"]) / "game-notes.json").read_text())
notes = document["notes"]
segments = document["segmentation"]
source_duration = float(os.environ["SOURCE_DURATION"])
silence_duration = 2.0
expected_shift = source_duration + silence_duration
first = [note for note in notes if note["start_seconds"] < source_duration + 0.1]
second = [note for note in notes if note["start_seconds"] > expected_shift - 0.1]
crossing = [
    note
    for note in notes
    if note["start_seconds"] < expected_shift - 0.1
    and note["end_seconds"] > source_duration + 0.1
]
segment_shift = segments["segments"][1]["offset_seconds"] - segments["segments"][0]["offset_seconds"]
checks = {
    "multiple_segments": len(segments["segments"]) >= 2,
    "non_overlapping_slices": segments["overlap_ms"] == 0,
    "offset_within_slicer_hop": abs(segment_shift - expected_shift) * 1000 <= 20,
    "equal_copy_note_counts": len(first) == len(second) and len(first) > 0,
    "no_notes_cross_inserted_silence": not crossing,
}
paired = list(zip(first, second, strict=len(first) == len(second)))
report = {
    "schema_version": "1.0",
    "date": "2026-09-07",
    "image_id": os.environ["IMAGE_ID"],
    "source_clip": "Vocadito vocadito_20.wav",
    "source_duration_seconds": source_duration,
    "inserted_silence_seconds": silence_duration,
    "synthetic_duration_seconds": float(os.environ["SYNTHETIC_DURATION"]),
    "segmentation": segments,
    "note_count": len(notes),
    "first_copy_note_count": len(first),
    "second_copy_note_count": len(second),
    "notes_crossing_inserted_silence": len(crossing),
    "segment_offset_shift_error_ms": round(abs(segment_shift - expected_shift) * 1000, 4),
    "pitch_mismatches_between_diffusion_samples": sum(
        left["pitch_midi"] != right["pitch_midi"] for left, right in paired
    ),
    "checks": checks,
    "passed": all(checks.values()),
}
Path(os.environ["OUTPUT"]).write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"passed": report["passed"], "checks": checks}, indent=2))
if not report["passed"]:
    raise SystemExit(1)
PY
