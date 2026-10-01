"""Run one GAME inference in an interruptible worker subprocess."""

import json
import os
import random
import sys
from pathlib import Path
from typing import Any

from vss_worker.device import resolve_inference_device

SEED = 114514


def main() -> None:
    source, target, model_path, game_root = map(Path, sys.argv[1:5])
    requested_device = sys.argv[5] if len(sys.argv) > 5 else None
    if requested_device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
    sys.path.insert(0, str(game_root))

    import lightning.pytorch  # type: ignore[import-not-found]
    import numpy as np  # type: ignore[import-not-found]
    import torch  # type: ignore[import-not-found]
    import torch.nn.functional as functional  # type: ignore[import-not-found]
    from inference.api import infer_model, load_inference_model  # type: ignore[import-not-found]
    from inference.data import SlicedAudioFileIterableDataset  # type: ignore[import-not-found]
    from inference.slicer2 import Slicer  # type: ignore[import-not-found]
    from lib.config.schema import ValidationConfig  # type: ignore[import-not-found]

    device = resolve_inference_device(requested_device)

    class NotesCallback(lightning.pytorch.Callback):  # type: ignore[misc]
        def __init__(self) -> None:
            self.notes: list[tuple[float, float, float]] = []
            self.segments: set[tuple[float, float]] = set()
            self.device = device

        def on_predict_batch_end(
            self,
            trainer: Any,
            pl_module: Any,
            outputs: dict[str, Any],
            batch: dict[str, Any],
            *args: Any,
        ) -> None:
            del trainer, pl_module, args
            scores = outputs.get("scores")
            if isinstance(scores, torch.Tensor):
                self.device = scores.device.type
            for index in range(batch["size"]):
                offset = float(batch["offset"][index])
                length = float(batch["length"][index])
                self.segments.add((offset, length))
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
                        self.notes.append((float(onset), float(note_offset), float(pitch)))

    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    if device == "cpu":
        torch.set_num_threads(max(1, os.cpu_count() or 1))
    else:
        torch.cuda.manual_seed_all(SEED)
    model, _ = load_inference_model(model_path)
    callback = NotesCallback()
    dataset = SlicedAudioFileIterableDataset(
        filemap={source.name: source},
        samplerate=model.inference_config.features.audio_sample_rate,
        slicer=Slicer(
            sr=model.inference_config.features.audio_sample_rate,
            threshold=-40.0,
            min_length=1000,
            min_interval=200,
            max_sil_kept=100,
        ),
        language=0,
    )
    infer_model(
        model=model,
        dataset=dataset,
        config=ValidationConfig(
            d3pm_sample_ts=[index / 8 for index in range(8)],
            boundary_decoding_threshold=0.10,
            boundary_decoding_radius=round(0.02 / model.timestep),
            note_presence_threshold=0.15,
        ),
        batch_size=4,
        num_workers=0,
        callbacks=[callback],
    )
    if callback.device != device:
        raise RuntimeError(
            f"GAME ran on {callback.device!r} after {device!r} was requested"
        )
    combined = []
    last_time = 0.0
    for onset, note_offset, pitch in sorted(callback.notes):
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
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "notes": notes,
                "segmentation": {
                    "method": "silence",
                    "threshold_db": -40.0,
                    "minimum_slice_ms": 1000,
                    "minimum_silence_ms": 200,
                    "maximum_silence_kept_ms": 100,
                    "overlap_ms": 0,
                    "segments": [
                        {"offset_seconds": offset, "duration_seconds": duration}
                        for offset, duration in sorted(callback.segments)
                    ],
                },
                "device": callback.device,
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
