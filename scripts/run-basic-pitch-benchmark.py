import argparse
import hashlib
import importlib.metadata
import json
import resource
import sys
import time
from dataclasses import asdict
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "workers" / "transcription"))

from basic_pitch import ICASSP_2022_MODEL_PATH  # type: ignore[import-not-found]  # noqa: E402
from vss_worker.basic_pitch_adapter import BasicPitchTranscriber  # noqa: E402
from vss_worker.melody import (  # noqa: E402
    diagnostics_document,
    quantized_notes,
    refine_melody,
)


def write_notes(
    path: Path, notes: list[dict[str, object]], *, metadata: dict[str, object] | None = None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({**(metadata or {}), "notes": notes}, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    paths = [path] if path.is_file() else sorted(item for item in path.rglob("*") if item.is_file())
    for item in paths:
        if path.is_dir():
            digest.update(item.relative_to(path).as_posix().encode())
        with item.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


parser = argparse.ArgumentParser(description="Run the fixed Basic Pitch P0 baseline")
parser.add_argument("audio_root", type=Path)
parser.add_argument("output_root", type=Path)
parser.add_argument("--bpm", type=float, default=120)
parser.add_argument("--limit", type=int)
parser.add_argument("--skip-existing", action="store_true")
arguments = parser.parse_args()
transcriber = BasicPitchTranscriber()
runtime_path = arguments.output_root / "runtime.json"
existing_runtime = {}
if runtime_path.is_file():
    previous = json.loads(runtime_path.read_text(encoding="utf-8"))
    for clip in previous.get("clips", []):
        if "duration_seconds" in clip and "elapsed_seconds" not in clip:
            clip["elapsed_seconds"] = clip.pop("duration_seconds")
        existing_runtime[clip["id"]] = clip
runtime = dict(existing_runtime)
audio_files = sorted(arguments.audio_root.glob("vocadito_*.wav"))
if arguments.limit is not None:
    audio_files = audio_files[: arguments.limit]
for index, audio in enumerate(audio_files):
    raw_path = arguments.output_root / "basic_pitch_raw" / f"{audio.stem}.json"
    expected_outputs = [
        raw_path,
        arguments.output_root / "basic_pitch_refined" / f"{audio.stem}.json",
        arguments.output_root / "basic_pitch_quantized" / f"{audio.stem}.json",
        arguments.output_root / "diagnostics" / f"{audio.stem}.json",
    ]
    if arguments.skip_existing and all(path.is_file() for path in expected_outputs):
        print(f"[{index + 1:02d}] {audio.name}: existing result skipped", flush=True)
        continue
    started = time.perf_counter()
    raw = sorted(transcriber.transcribe(audio), key=lambda note: note.start_seconds)
    elapsed = time.perf_counter() - started
    refined = refine_melody(raw)
    write_notes(
        raw_path,
        [asdict(note) for note in raw],
    )
    write_notes(
        arguments.output_root / "basic_pitch_refined" / f"{audio.stem}.json",
        [asdict(note) for note in refined],
    )
    write_notes(
        arguments.output_root / "basic_pitch_quantized" / f"{audio.stem}.json",
        quantized_notes(refined, arguments.bpm),
        metadata={"bpm": arguments.bpm},
    )
    diagnostics = diagnostics_document(raw, arguments.bpm)
    diagnostics_path = arguments.output_root / "diagnostics" / f"{audio.stem}.json"
    diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics_path.write_text(json.dumps(diagnostics, indent=2) + "\n", encoding="utf-8")
    runtime[audio.stem] = {
        "id": audio.stem,
        "elapsed_seconds": elapsed,
        "raw_note_count": len(raw),
        "refined_note_count": len(refined),
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    print(f"[{index + 1:02d}] {audio.name}: {len(raw)} notes in {elapsed:.2f}s", flush=True)

arguments.output_root.mkdir(parents=True, exist_ok=True)
model_path = Path(ICASSP_2022_MODEL_PATH)
summary = {
    "schema_version": "1.0",
    "engine": "basic_pitch",
    "package_version": importlib.metadata.version("basic-pitch"),
    "model_path": str(model_path),
    "model_sha256": sha256(model_path),
    "device": "cpu",
    "bpm_for_quantized_variant": arguments.bpm,
    "clips": [runtime[key] for key in sorted(runtime)],
}
runtime_path.write_text(
    json.dumps(summary, indent=2) + "\n", encoding="utf-8"
)
