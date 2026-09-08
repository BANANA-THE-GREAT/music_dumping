"""Small deterministic harmonic synthesizer for F0 listening diagnostics."""

from __future__ import annotations

import json
import math
import struct
import wave
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class F0Frame:
    time_seconds: float
    f0_hz: float
    periodicity: float


def read_f0_jsonl(path: Path) -> list[F0Frame]:
    frames: list[F0Frame] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        frames.append(
            F0Frame(
                time_seconds=float(value["time_seconds"]),
                f0_hz=float(value["f0_hz"]),
                periodicity=float(value["periodicity"]),
            )
        )
    frames.sort(key=lambda frame: frame.time_seconds)
    if any(frame.time_seconds < 0 for frame in frames):
        raise ValueError("F0 frame times must be non-negative")
    return frames


def synthesize_harmonic(
    frames: list[F0Frame],
    *,
    sample_rate: int = 16_000,
    periodicity_threshold: float = 0.5,
    harmonics: int = 8,
    amplitude: float = 0.35,
) -> tuple[bytes, dict[str, object]]:
    if sample_rate <= 0 or harmonics <= 0:
        raise ValueError("sample_rate and harmonics must be positive")
    if not 0 <= periodicity_threshold <= 1:
        raise ValueError("periodicity_threshold must be between 0 and 1")
    if amplitude <= 0:
        raise ValueError("amplitude must be positive")
    if not frames:
        return b"", {"frame_count": 0, "voiced_frame_count": 0, "duration_seconds": 0}

    duration = frames[-1].time_seconds + (
        frames[1].time_seconds - frames[0].time_seconds if len(frames) > 1 else 0.01
    )
    frame_period = (
        frames[1].time_seconds - frames[0].time_seconds if len(frames) > 1 else 0.01
    )
    if frame_period <= 0:
        raise ValueError("F0 frame times must be strictly increasing")
    if any(right.time_seconds <= left.time_seconds for left, right in zip(frames, frames[1:])):
        raise ValueError("F0 frame times must be strictly increasing")

    sample_count = round(duration * sample_rate)
    output = bytearray()
    phase = 0.0
    frame_index = 0
    voiced_count = sum(
        1 for frame in frames if frame.periodicity >= periodicity_threshold and frame.f0_hz > 0
    )
    for sample_index in range(sample_count):
        time_seconds = sample_index / sample_rate
        while frame_index + 1 < len(frames) and frames[frame_index + 1].time_seconds <= time_seconds:
            frame_index += 1
        frame = frames[frame_index]
        voiced = frame.periodicity >= periodicity_threshold and frame.f0_hz > 0
        if voiced:
            harmonic = sum(math.sin(phase * partial) / partial for partial in range(1, harmonics + 1))
            value = amplitude * min(1.0, frame.periodicity) * harmonic / sum(1 / p for p in range(1, harmonics + 1))
            phase += 2 * math.pi * frame.f0_hz / sample_rate
        else:
            value = 0.0
        clipped = max(-1.0, min(1.0, value))
        output.extend(struct.pack("<h", round(clipped * 32767)))
    return bytes(output), {
        "frame_count": len(frames),
        "voiced_frame_count": voiced_count,
        "duration_seconds": duration,
        "sample_rate": sample_rate,
        "periodicity_threshold": periodicity_threshold,
        "harmonics": harmonics,
        "amplitude": amplitude,
    }


def write_wav(path: Path, pcm: bytes, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm)
