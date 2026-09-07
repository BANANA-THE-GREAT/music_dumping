import argparse
import hashlib
import importlib
import json
import os
import random
import resource
import sys
import time
from pathlib import Path

import librosa
import numpy as np
import torch
import yaml

SEED = 114514


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_model(model_path: Path):
    from inference import BaseInference, task_inference_mapping

    config = yaml.safe_load(model_path.with_name("config.yaml").read_text(encoding="utf-8"))
    inference_class = task_inference_mapping[config["task_cls"]]
    package, class_name = inference_class.rsplit(".", 1)
    model_class = getattr(importlib.import_module(package), class_name)
    if not issubclass(model_class, BaseInference):
        raise TypeError(f"Unsupported SOME inference class: {inference_class}")
    return model_class(config=config, model_path=model_path, device="cpu"), config


def transcribe(audio_path: Path, model, config: dict[str, object]) -> list[dict[str, object]]:
    from utils.slicer2 import Slicer

    sample_rate = int(config["audio_sample_rate"])
    waveform, _ = librosa.load(audio_path, sr=sample_rate, mono=True)
    chunks = Slicer(sr=sample_rate, max_sil_kept=1000).slice(waveform)
    segments = model.infer([chunk["waveform"] for chunk in chunks])
    notes = []
    for chunk, segment in zip(chunks, segments, strict=True):
        current = float(chunk["offset"])
        for pitch, duration, is_rest in zip(
            segment["note_midi"].tolist(),
            segment["note_dur"].tolist(),
            segment["note_rest"].tolist(),
            strict=True,
        ):
            end = current + float(duration)
            if not is_rest and end > current:
                notes.append(
                    {
                        "start_seconds": current,
                        "end_seconds": end,
                        "pitch_midi": round(float(pitch)),
                        "confidence": 1.0,
                        "source_id": f"some-{len(notes):04d}",
                        "pitch_cents": float(pitch) * 100,
                    }
                )
            current = end
    return notes


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a fixed SOME Vocadito benchmark")
    parser.add_argument("audio_root", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("--variant", default="some_continuous256_5spk")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--skip-existing", action="store_true")
    arguments = parser.parse_args()

    sys.path.insert(0, "/opt/some")
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.set_num_threads(max(1, os.cpu_count() or 1))

    load_started = time.perf_counter()
    model, config = load_model(arguments.model)
    load_seconds = time.perf_counter() - load_started
    output_dir = arguments.output_root / arguments.variant
    audio_files = sorted(arguments.audio_root.glob("vocadito_*.wav"))
    if arguments.limit is not None:
        audio_files = audio_files[: arguments.limit]
    clips = []
    failures = []
    for audio in audio_files:
        output_path = output_dir / f"{audio.stem}.json"
        if arguments.skip_existing and output_path.is_file():
            continue
        try:
            random.seed(SEED)
            np.random.seed(SEED)
            torch.manual_seed(SEED)
            started = time.perf_counter()
            notes = transcribe(audio, model, config)
            elapsed = time.perf_counter() - started
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps({"notes": notes}, indent=2) + "\n", encoding="utf-8")
            clips.append(
                {"id": audio.stem, "elapsed_seconds": elapsed, "note_count": len(notes)}
            )
            print(f"{audio.name}: {len(notes)} notes in {elapsed:.2f}s", flush=True)
        except Exception as error:
            failures.append({"id": audio.stem, "error": str(error)})

    runtime = {
        "schema_version": "1.0",
        "engine": "some",
        "variant": arguments.variant,
        "upstream_commit": os.environ.get("SOME_COMMIT"),
        "model_sha256": sha256(arguments.model),
        "device": "cpu",
        "seed": SEED,
        "model_load_seconds": load_seconds,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
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
