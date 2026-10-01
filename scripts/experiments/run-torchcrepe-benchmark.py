import argparse
import hashlib
import json
import os
import resource
import sys
import time
from pathlib import Path

import numpy as np
import soundfile
import torch
import torchcrepe


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def selected_audio(audio_root: Path, manifest_path: Path, split: str) -> list[Path]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    selected_ids = {clip["id"] for clip in manifest["clips"] if clip["split"] == split}
    return [
        path
        for path in sorted(audio_root.glob("vocadito_*.wav"))
        if path.stem in selected_ids
    ]


def predict(audio_path: Path, batch_size: int, device: str) -> dict[str, object]:
    waveform, sample_rate = soundfile.read(
        audio_path, dtype="float32", always_2d=True
    )
    mono = torch.from_numpy(np.mean(waveform, axis=1, dtype=np.float32)).unsqueeze(0)
    hop_length = round(sample_rate / 100)
    pitch, periodicity = torchcrepe.predict(
        mono,
        sample_rate,
        hop_length,
        50.0,
        1100.0,
        "full",
        decoder=torchcrepe.decode.viterbi,
        return_periodicity=True,
        batch_size=batch_size,
        device=device,
        pad=True,
    )
    periodicity = torchcrepe.filter.median(periodicity, 3)
    periodicity = torchcrepe.threshold.Silence(-60.0)(
        periodicity, mono, sample_rate, hop_length
    )
    frame_count = min(pitch.shape[-1], periodicity.shape[-1])
    return {
        "schema_version": "1.0",
        "sample_rate": sample_rate,
        "hop_length": hop_length,
        "times_seconds": [index * hop_length / sample_rate for index in range(frame_count)],
        "f0_hz": pitch[0, :frame_count].tolist(),
        "periodicity": periodicity[0, :frame_count].tolist(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run torchcrepe on a Vocadito split")
    parser.add_argument("audio_root", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--split", choices=("tuning", "holdout"), default="tuning")
    parser.add_argument("--variant", default="torchcrepe_full")
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    arguments = parser.parse_args()

    if arguments.device == "cpu":
        torch.set_num_threads(max(1, os.cpu_count() or 1))
    else:
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false")
        torch.cuda.reset_peak_memory_stats()
    model_path = Path(torchcrepe.__file__).parent / "assets" / "full.pth"
    audio_files = selected_audio(arguments.audio_root, arguments.manifest, arguments.split)
    if arguments.limit is not None:
        audio_files = audio_files[: arguments.limit]
    output_dir = arguments.output_root / arguments.variant
    clips = []
    failures = []
    for audio_path in audio_files:
        try:
            started = time.perf_counter()
            frames = predict(audio_path, arguments.batch_size, arguments.device)
            elapsed = time.perf_counter() - started
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / f"{audio_path.stem}.json").write_text(
                json.dumps(frames, separators=(",", ":")) + "\n", encoding="utf-8"
            )
            clips.append(
                {
                    "id": audio_path.stem,
                    "elapsed_seconds": elapsed,
                    "frame_count": len(frames["f0_hz"]),
                }
            )
            print(f"{audio_path.name}: {len(frames['f0_hz'])} frames in {elapsed:.2f}s")
        except Exception as error:
            failures.append({"id": audio_path.stem, "error": str(error)})

    runtime = {
        "schema_version": "1.0",
        "engine": "torchcrepe",
        "variant": arguments.variant,
        "upstream_commit": os.environ.get("TORCHCREPE_COMMIT"),
        "model_sha256": sha256(model_path),
        "device": arguments.device,
        "parameters": {
            "split": arguments.split,
            "model": "full",
            "hop_ms": 10,
            "fmin_hz": 50,
            "fmax_hz": 1100,
            "decoder": "viterbi",
            "periodicity_median_frames": 3,
            "silence_threshold_db": -60,
            "batch_size": arguments.batch_size,
        },
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "peak_cuda_memory_bytes": (
            torch.cuda.max_memory_allocated() if arguments.device == "cuda" else 0
        ),
        "clips": clips,
        "failures": failures,
    }
    arguments.output_root.mkdir(parents=True, exist_ok=True)
    (arguments.output_root / f"runtime-{arguments.variant}.json").write_text(
        json.dumps(runtime, indent=2) + "\n", encoding="utf-8"
    )
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(1 if failures else 0)


if __name__ == "__main__":
    main()
