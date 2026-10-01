"""Constrained melody decoding on top of neural polyphonic note detections."""

from dataclasses import asdict, dataclass, replace
from math import isfinite
from typing import Literal, cast

from vss_worker.adapters import DetectedNote


@dataclass(frozen=True)
class RefinementConfig:
    mode: Literal["raw", "conservative", "balanced"] = "balanced"
    low_pitch: int = 48
    high_pitch: int = 84
    minimum_duration_seconds: float = 0.06
    minimum_confidence: float = 0.2
    apply_pitch_range: bool = True
    apply_continuity: bool = True
    stitch_short_fragments: bool = True


@dataclass(frozen=True)
class NoteDecision:
    source_ids: tuple[str, ...]
    action: Literal["keep", "filter", "merge", "quantize_conflict"]
    reason: str


@dataclass(frozen=True)
class RefinementResult:
    notes: list[DetectedNote]
    decisions: list[NoteDecision]
    config: RefinementConfig


@dataclass(frozen=True)
class QuantizationConfig:
    grid: float = 0.25
    monophonic: bool = True
    resolve_start_conflicts: bool = True


@dataclass(frozen=True)
class QuantizationResult:
    notes: list[dict[str, object]]
    decisions: list[NoteDecision]
    config: QuantizationConfig


def _identified(notes: list[DetectedNote]) -> list[DetectedNote]:
    return [
        note if note.source_id is not None else replace(note, source_id=f"raw-{index:06d}")
        for index, note in enumerate(notes)
    ]


def refine_melody_with_diagnostics(
    notes: list[DetectedNote], config: RefinementConfig | None = None
) -> RefinementResult:
    config = config or RefinementConfig()
    identified = _identified(notes)
    if config.mode == "raw":
        return RefinementResult(
            notes=identified,
            decisions=[
                NoteDecision((note.source_id or "",), "keep", "raw_mode") for note in identified
            ],
            config=config,
        )
    decisions: list[NoteDecision] = []
    candidates: list[DetectedNote] = []
    for detected_note in identified:
        source_ids = (detected_note.source_id or "",)
        values = (
            detected_note.start_seconds,
            detected_note.end_seconds,
            detected_note.confidence,
        )
        if not all(isfinite(value) for value in values) or (
            detected_note.end_seconds <= detected_note.start_seconds
        ):
            decisions.append(NoteDecision(source_ids, "filter", "invalid_timing_or_confidence"))
        elif config.apply_pitch_range and not (
            config.low_pitch <= detected_note.pitch_midi <= config.high_pitch
        ):
            decisions.append(NoteDecision(source_ids, "filter", "outside_pitch_range"))
        elif (
            detected_note.end_seconds - detected_note.start_seconds
            < config.minimum_duration_seconds
        ):
            decisions.append(NoteDecision(source_ids, "filter", "shorter_than_minimum_duration"))
        elif detected_note.confidence < config.minimum_confidence:
            decisions.append(NoteDecision(source_ids, "filter", "below_minimum_confidence"))
        else:
            candidates.append(detected_note)
    candidates.sort(key=lambda note: note.start_seconds)
    if not candidates:
        return RefinementResult([], decisions, config)
    if not config.apply_continuity:
        decisions.extend(
            NoteDecision((note.source_id or "",), "keep", "continuity_disabled")
            for note in candidates
        )
        return RefinementResult(candidates, decisions, config)

    boundaries = sorted(
        {
            value
            for detected_note in candidates
            for value in (detected_note.start_seconds, detected_note.end_seconds)
        }
    )
    layers: list[dict[int, tuple[float, int | None]]] = []
    active: set[int] = set()
    pointer = 0
    previous: dict[int, tuple[float, int | None]] = {-1: (0, None)}
    continuity = 0.025 if config.mode == "conservative" else 0.05
    for start, end in zip(boundaries, boundaries[1:], strict=False):
        active = {index for index in active if candidates[index].end_seconds > start}
        while pointer < len(candidates) and candidates[pointer].start_seconds <= start:
            active.add(pointer)
            pointer += 1
        states = (
            sorted(active, key=lambda index: candidates[index].confidence, reverse=True)[:8]
            or [-1]
        )
        layer: dict[int, tuple[float, int | None]] = {}
        for index in states:
            emission = 0 if index == -1 else (end - start) * candidates[index].confidence
            options = []
            for prior_index in previous:
                penalty = 0.0
                if index >= 0 and prior_index >= 0 and index != prior_index:
                    leap = abs(
                        candidates[index].pitch_midi - candidates[prior_index].pitch_midi
                    )
                    penalty = continuity * min(leap, 12) + (0.02 if leap else 0)
                options.append((previous[prior_index][0] + emission - penalty, prior_index))
            layer[index] = max(options)
        layers.append(layer)
        previous = layer
    state: int | None = max(previous, key=lambda index: previous[index][0])
    path: list[int] = []
    for layer in reversed(layers):
        if state is None:
            break
        path.append(state)
        state = layer[state][1]
    selected_indexes = {index for index in path if index >= 0}
    for index, note in enumerate(candidates):
        if index not in selected_indexes:
            decisions.append(NoteDecision((note.source_id or "",), "filter", "continuity_path"))
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
        if note.end_seconds - note.start_seconds < config.minimum_duration_seconds:
            decisions.append(
                NoteDecision((note.source_id or "",), "filter", "selected_fragment_too_short")
            )
            continue
        prior_note = result[-1] if result else None
        stitch_gap = 0.04 if config.mode == "conservative" else 0.08
        should_stitch = (
            config.stitch_short_fragments
            and prior_note is not None
            and prior_note.pitch_midi == note.pitch_midi
            and 0 <= note.start_seconds - prior_note.end_seconds <= stitch_gap
            and min(
                prior_note.end_seconds - prior_note.start_seconds,
                note.end_seconds - note.start_seconds,
            )
            < 0.18
        )
        if should_stitch and prior_note is not None:
            merged_ids = tuple(filter(None, (prior_note.source_id, note.source_id)))
            result[-1] = replace(
                prior_note,
                end_seconds=note.end_seconds,
                confidence=min(prior_note.confidence, note.confidence),
                source_id="+".join(merged_ids),
            )
            decisions.append(NoteDecision(merged_ids, "merge", "short_same_pitch_fragments"))
        else:
            result.append(note)
            decisions.append(NoteDecision((note.source_id or "",), "keep", "continuity_path"))
    return RefinementResult(result, decisions, config)


def refine_melody(
    notes: list[DetectedNote], mode: str = "balanced", low: int = 48, high: int = 84
) -> list[DetectedNote]:
    if mode == "raw":
        return list(notes)
    if mode not in {"raw", "conservative", "balanced"}:
        raise ValueError(f"Unknown refinement mode: {mode}")
    return refine_melody_with_diagnostics(
        notes,
        RefinementConfig(
            mode=mode,  # type: ignore[arg-type]
            low_pitch=low,
            high_pitch=high,
        ),
    ).notes


def quantized_notes(
    notes: list[DetectedNote], bpm: float, *, monophonic: bool = True, grid: float = 0.25
) -> list[dict[str, object]]:
    return quantize_with_diagnostics(
        notes,
        bpm,
        QuantizationConfig(grid=grid, monophonic=monophonic),
    ).notes


def quantize_with_diagnostics(
    notes: list[DetectedNote], bpm: float, config: QuantizationConfig | None = None
) -> QuantizationResult:
    from uuid import NAMESPACE_URL, uuid5

    config = config or QuantizationConfig()
    if bpm <= 0:
        raise ValueError("bpm must be positive")
    if config.grid <= 0:
        raise ValueError("grid must be positive")
    beat = 60 / bpm
    result: list[dict[str, object]] = []
    decisions: list[NoteDecision] = []
    for detected_note in _identified(notes):
        start = round(detected_note.start_seconds / beat / config.grid) * config.grid
        end = round(detected_note.end_seconds / beat / config.grid) * config.grid
        identity = ":".join(
            (
                detected_note.source_id or "",
                str(detected_note.start_seconds),
                str(detected_note.end_seconds),
                str(detected_note.pitch_midi),
            )
        )
        result.append(
            {
                "id": str(uuid5(NAMESPACE_URL, identity)),
                "source_start_ms": round(detected_note.start_seconds * 1000),
                "source_end_ms": round(detected_note.end_seconds * 1000),
                "source_note_ids": [detected_note.source_id],
                "pitch_midi": detected_note.pitch_midi,
                "confidence": detected_note.confidence,
                "quantized_start": start,
                "quantized_duration": max(config.grid, end - start),
                "origin": "model",
            }
        )
    if config.monophonic and config.resolve_start_conflicts:
        by_start: dict[object, dict[str, object]] = {}
        for quantized_note in result:
            quantized_start = cast(float, quantized_note["quantized_start"])
            prior_quantized = by_start.get(quantized_start)
            confidence = cast(float, quantized_note["confidence"])
            prior_confidence = (
                cast(float, prior_quantized["confidence"])
                if prior_quantized is not None
                else None
            )
            if prior_quantized is None or (
                prior_confidence is not None and confidence > prior_confidence
            ):
                if prior_quantized is not None:
                    decisions.append(
                        NoteDecision(
                            tuple(
                                str(value)
                                for value in cast(list[object], prior_quantized["source_note_ids"])
                            ),
                            "quantize_conflict",
                            "lower_confidence_same_grid_start",
                        )
                    )
                by_start[quantized_start] = quantized_note
            else:
                decisions.append(
                    NoteDecision(
                        tuple(
                            str(value)
                            for value in cast(list[object], quantized_note["source_note_ids"])
                        ),
                        "quantize_conflict",
                        "lower_confidence_same_grid_start",
                    )
                )
        result = list(by_start.values())
    result.sort(
        key=lambda item: (
            cast(float, item["quantized_start"]),
            cast(int, item["pitch_midi"]),
        )
    )
    # Do not let minimum grid durations introduce overlapping melody notes.
    for left, right in zip(result, result[1:], strict=False):
        left_start = cast(float, left["quantized_start"])
        right_start = cast(float, right["quantized_start"])
        if config.monophonic and left_start < right_start:
            left["quantized_duration"] = min(
                cast(float, left["quantized_duration"]),
                right_start - left_start,
            )
    return QuantizationResult(result, decisions, config)


def diagnostics_document(
    raw_notes: list[DetectedNote],
    bpm: float,
    refinement: RefinementConfig | None = None,
    quantization: QuantizationConfig | None = None,
) -> dict[str, object]:
    refined = refine_melody_with_diagnostics(raw_notes, refinement)
    quantized = quantize_with_diagnostics(refined.notes, bpm, quantization)
    return {
        "schema_version": "1.0",
        "bpm": bpm,
        "refinement_config": asdict(refined.config),
        "quantization_config": asdict(quantized.config),
        "raw_notes": [asdict(note) for note in _identified(raw_notes)],
        "refined_notes": [asdict(note) for note in refined.notes],
        "quantized_notes": quantized.notes,
        "decisions": [
            asdict(decision) for decision in [*refined.decisions, *quantized.decisions]
        ],
    }
