"""Constrained melody decoding on top of neural polyphonic note detections."""

from dataclasses import replace
from math import isfinite

from vss_worker.adapters import DetectedNote


def refine_melody(
    notes: list[DetectedNote], mode: str = "balanced", low: int = 48, high: int = 84
) -> list[DetectedNote]:
    if mode == "raw":
        return list(notes)
    candidates = sorted(
        (
            n
            for n in notes
            if low <= n.pitch_midi <= high
            and all(isfinite(v) for v in (n.start_seconds, n.end_seconds, n.confidence))
            and n.end_seconds - n.start_seconds >= 0.06
            and n.confidence >= 0.2
        ),
        key=lambda n: n.start_seconds,
    )
    if not candidates:
        return []
    boundaries = sorted({v for n in candidates for v in (n.start_seconds, n.end_seconds)})
    layers: list[dict[int, tuple[float, int | None]]] = []
    active: set[int] = set()
    pointer = 0
    previous: dict[int, tuple[float, int | None]] = {-1: (0, None)}
    continuity = 0.025 if mode == "conservative" else 0.05
    for start, end in zip(boundaries, boundaries[1:], strict=False):
        active = {i for i in active if candidates[i].end_seconds > start}
        while pointer < len(candidates) and candidates[pointer].start_seconds <= start:
            active.add(pointer)
            pointer += 1
        states = sorted(active, key=lambda i: candidates[i].confidence, reverse=True)[:8] or [-1]
        layer: dict[int, tuple[float, int | None]] = {}
        for index in states:
            emission = 0 if index == -1 else (end - start) * candidates[index].confidence
            options = []
            for prior in previous:
                penalty = 0.0
                if index >= 0 and prior >= 0 and index != prior:
                    leap = abs(candidates[index].pitch_midi - candidates[prior].pitch_midi)
                    penalty = continuity * min(leap, 12) + (0.02 if leap else 0)
                options.append((previous[prior][0] + emission - penalty, prior))
            layer[index] = max(options)
        layers.append(layer)
        previous = layer
    state = max(previous, key=lambda i: previous[i][0])
    path = []
    for layer in reversed(layers):
        path.append(state)
        state = layer[state][1]
    fragments: list[tuple[int, DetectedNote]] = []
    for index, start, end in zip(reversed(path), boundaries, boundaries[1:], strict=False):
        if index < 0:
            continue
        if (
            fragments
            and fragments[-1][0] == index
            and abs(fragments[-1][1].end_seconds - start) < 1e-8
        ):
            fragments[-1] = index, replace(fragments[-1][1], end_seconds=end)
        else:
            fragments.append(
                (index, replace(candidates[index], start_seconds=start, end_seconds=end))
            )
    result: list[DetectedNote] = []
    for _, note in fragments:
        if note.end_seconds - note.start_seconds < 0.06:
            continue
        prior = result[-1] if result else None
        # Only stitch very short same-pitch fragments; retain full repeated notes and breaths.
        if (
            prior
            and prior.pitch_midi == note.pitch_midi
            and 0
            <= note.start_seconds - prior.end_seconds
            <= (0.04 if mode == "conservative" else 0.08)
            and min(prior.end_seconds - prior.start_seconds, note.end_seconds - note.start_seconds)
            < 0.18
        ):
            result[-1] = replace(
                prior,
                end_seconds=note.end_seconds,
                confidence=min(prior.confidence, note.confidence),
            )
        else:
            result.append(note)
    return result


def quantized_notes(
    notes: list[DetectedNote], bpm: float, *, monophonic: bool = True
) -> list[dict[str, object]]:
    from uuid import uuid4

    beat = 60 / bpm
    result = []
    for n in notes:
        start = round(n.start_seconds / beat * 4) / 4
        end = round(n.end_seconds / beat * 4) / 4
        result.append(
            {
                "id": str(uuid4()),
                "source_start_ms": round(n.start_seconds * 1000),
                "source_end_ms": round(n.end_seconds * 1000),
                "pitch_midi": n.pitch_midi,
                "confidence": n.confidence,
                "quantized_start": start,
                "quantized_duration": max(0.25, end - start),
                "origin": "model",
            }
        )
    if monophonic:
        by_start = {}
        for note in result:
            prior = by_start.get(note["quantized_start"])
            if prior is None or note["confidence"] > prior["confidence"]:
                by_start[note["quantized_start"]] = note
        result = list(by_start.values())
    # Do not let minimum grid durations introduce overlapping melody notes.
    for left, right in zip(result, result[1:], strict=False):
        if monophonic and left["quantized_start"] < right["quantized_start"]:
            left["quantized_duration"] = min(
                left["quantized_duration"], right["quantized_start"] - left["quantized_start"]
            )
    return result
