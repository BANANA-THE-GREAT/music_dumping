"""Write a 10 ms torchcrepe F0 track as newline-delimited JSON."""

import json
import os
import sys
from pathlib import Path


def main() -> None:
    source, target = map(Path, sys.argv[1:3])
    requested_device = sys.argv[3] if len(sys.argv) > 3 else None
    import numpy as np  # type: ignore[import-not-found]
    import soundfile  # type: ignore[import-not-found]
    import torch  # type: ignore[import-not-found]
    import torchcrepe  # type: ignore[import-not-found]

    from vss_worker.device import resolve_inference_device

    device = resolve_inference_device(requested_device)
    if device == "cpu":
        torch.set_num_threads(max(1, os.cpu_count() or 1))
    waveform, sample_rate = soundfile.read(source, dtype="float32", always_2d=True)
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
        batch_size=512,
        device=device,
        pad=True,
    )
    periodicity = torchcrepe.filter.median(periodicity, 3)
    periodicity = torchcrepe.threshold.Silence(-60.0)(
        periodicity, mono, sample_rate, hop_length
    )
    frame_count = min(pitch.shape[-1], periodicity.shape[-1])
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as output:
        for index in range(frame_count):
            output.write(
                json.dumps(
                    {
                        "time_seconds": index * hop_length / sample_rate,
                        "f0_hz": float(pitch[0, index]),
                        "periodicity": float(periodicity[0, index]),
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )


if __name__ == "__main__":
    main()
