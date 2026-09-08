import argparse
import hashlib
import json
import os
import random
import resource
import sys
import time
from pathlib import Path

import lightning.pytorch
import numpy as np
import torch
import torch.nn.functional as functional

SEED = 114514


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a fixed GAME Vocadito benchmark")
    parser.add_argument("audio_root", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--split", choices=("tuning", "holdout"))
    parser.add_argument("--boundary-threshold", type=float, default=0.2)
    parser.add_argument("--presence-threshold", type=float, default=0.2)
    parser.add_argument("--d3pm-steps", type=int, default=8)
    parser.add_argument("--language-id", type=int, default=0)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    arguments = parser.parse_args()
    if arguments.split and arguments.manifest is None:
        parser.error("--split requires --manifest")
    if not 0 <= arguments.boundary_threshold <= 1:
        parser.error("--boundary-threshold must be between 0 and 1")
    if not 0 <= arguments.presence_threshold <= 1:
        parser.error("--presence-threshold must be between 0 and 1")
    if arguments.d3pm_steps < 2:
        parser.error("--d3pm-steps must be at least 2")

    sys.path.insert(0, "/opt/game")
    from inference.api import infer_model, load_inference_model
    from inference.data import SlicedAudioFileIterableDataset
    from inference.slicer2 import Slicer
    from lib.config.schema import ValidationConfig

    class JsonNotesCallback(lightning.pytorch.Callback):
        def __init__(self, destination: Path) -> None:
            self.destination = destination
            self.counters: dict[str, int] = {}
            self.notes: dict[str, list[tuple[float, float, float]]] = {}
            self.note_counts: dict[str, int] = {}

        def on_predict_batch_end(self, trainer, pl_module, outputs, batch, *args) -> None:
            for index in range(batch["size"]):
                key = batch["key"][index]
                self.counters.setdefault(key, 0)
                self.notes.setdefault(key, [])
                offset = float(batch["offset"][index])
                length = float(batch["length"][index])
                durations = outputs["durations"][index]
                onsets = functional.pad(durations, (1, 0), value=0).cumsum(0)
                onsets = onsets.clamp(max=length).add(offset)
                offsets = durations.cumsum(0).clamp(max=length).add(offset)
                for onset, note_offset, pitch, present in zip(
                    onsets.tolist(),
                    offsets.tolist(),
                    outputs["scores"][index].tolist(),
                    outputs["presence"][index].tolist(),
                    strict=False,
                ):
                    if present and note_offset > onset:
                        self.notes[key].append((onset, note_offset, pitch))
                self.counters[key] += 1
                if self.counters[key] >= batch["num_parts"][index]:
                    self.flush(key)

        def on_predict_epoch_end(self, trainer, pl_module) -> None:
            for key in list(self.notes):
                self.flush(key)

        def flush(self, key: str) -> None:
            if key not in self.notes:
                return
            combined = []
            last_time = 0.0
            for onset, note_offset, pitch in sorted(self.notes.pop(key)):
                onset = max(onset, last_time)
                note_offset = max(note_offset, onset)
                if note_offset <= onset:
                    continue
                combined.append((onset, note_offset, pitch))
                last_time = note_offset
            notes = [
                {
                    "start_seconds": onset,
                    "end_seconds": note_offset,
                    "pitch_midi": round(pitch),
                    "confidence": 1.0,
                    "source_id": f"game-{index:04d}",
                    "pitch_cents": pitch * 100,
                }
                for index, (onset, note_offset, pitch) in enumerate(combined)
            ]
            stem = Path(key).stem
            path = self.destination / f"{stem}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"notes": notes}, indent=2) + "\n", encoding="utf-8")
            self.note_counts[stem] = len(notes)
            self.counters.pop(key, None)

    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    if arguments.device == "cpu":
        torch.set_num_threads(max(1, os.cpu_count() or 1))
    else:
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false")
        torch.cuda.manual_seed_all(SEED)
        torch.cuda.reset_peak_memory_stats()

    audio_files = sorted(arguments.audio_root.glob("vocadito_*.wav"))
    if arguments.manifest is not None:
        manifest = json.loads(arguments.manifest.read_text(encoding="utf-8"))
        selected_ids = {
            clip["id"]
            for clip in manifest["clips"]
            if arguments.split is None or clip["split"] == arguments.split
        }
        audio_files = [audio for audio in audio_files if audio.stem in selected_ids]
    if arguments.limit is not None:
        audio_files = audio_files[: arguments.limit]
    output_dir = arguments.output_root / arguments.variant
    if arguments.skip_existing:
        audio_files = [
            audio
            for audio in audio_files
            if not (output_dir / f"{audio.stem}.json").is_file()
        ]

    load_started = time.perf_counter()
    model, _ = load_inference_model(arguments.model)
    load_seconds = time.perf_counter() - load_started
    inference_seconds = 0.0
    failures = []
    note_counts = {}
    if audio_files:
        callback = JsonNotesCallback(output_dir)
        filemap = {audio.name: audio for audio in audio_files}
        dataset = SlicedAudioFileIterableDataset(
            filemap=filemap,
            samplerate=model.inference_config.features.audio_sample_rate,
            slicer=Slicer(
                sr=model.inference_config.features.audio_sample_rate,
                threshold=-40.0,
                min_length=1000,
                min_interval=200,
                max_sil_kept=100,
            ),
            language=arguments.language_id,
        )
        random.seed(SEED)
        np.random.seed(SEED)
        torch.manual_seed(SEED)
        started = time.perf_counter()
        infer_model(
            model=model,
            dataset=dataset,
            config=ValidationConfig(
                d3pm_sample_ts=[
                    index / arguments.d3pm_steps for index in range(arguments.d3pm_steps)
                ],
                boundary_decoding_threshold=arguments.boundary_threshold,
                boundary_decoding_radius=round(0.02 / model.timestep),
                note_presence_threshold=arguments.presence_threshold,
            ),
            batch_size=arguments.batch_size,
            num_workers=0,
            callbacks=[callback],
        )
        inference_seconds = time.perf_counter() - started
        note_counts.update(callback.note_counts)
        for audio in audio_files:
            if audio.stem not in note_counts:
                failures.append({"id": audio.stem, "error": "missing output"})

    runtime = {
        "schema_version": "1.0",
        "engine": "game",
        "variant": arguments.variant,
        "upstream_commit": os.environ.get("GAME_COMMIT"),
        "model_sha256": sha256(arguments.model),
        "device": arguments.device,
        "seed": SEED,
        "parameters": {
            "manifest": str(arguments.manifest) if arguments.manifest else None,
            "split": arguments.split,
            "language_id": arguments.language_id,
            "batch_size": arguments.batch_size,
            "seg_threshold": arguments.boundary_threshold,
            "seg_radius_seconds": 0.02,
            "d3pm_t0": 0.0,
            "d3pm_nsteps": arguments.d3pm_steps,
            "est_threshold": arguments.presence_threshold,
        },
        "model_load_seconds": load_seconds,
        "inference_seconds": inference_seconds,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "peak_cuda_memory_bytes": (
            torch.cuda.max_memory_allocated() if arguments.device == "cuda" else 0
        ),
        "clip_count": len(note_counts),
        "failures": failures,
        "note_counts": note_counts,
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
