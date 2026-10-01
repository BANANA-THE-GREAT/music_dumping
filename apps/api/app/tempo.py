from collections.abc import Sequence

from app.schemas import TempoPoint


def beat_at_ms(time_ms: int, tempo_map: Sequence[TempoPoint]) -> float:
    """Convert an absolute audio timestamp to beats through a piecewise tempo map."""
    if not tempo_map or tempo_map[0].time_ms != 0:
        raise ValueError("tempo_map must start at 0 ms")
    if time_ms < 0:
        return time_ms / (60_000 / tempo_map[0].bpm)
    beats = 0.0
    for index, point in enumerate(tempo_map):
        end_ms = (
            tempo_map[index + 1].time_ms
            if index + 1 < len(tempo_map)
            else time_ms
        )
        if time_ms <= point.time_ms:
            break
        segment_end = min(time_ms, end_ms)
        beats += (segment_end - point.time_ms) / (60_000 / point.bpm)
        if segment_end >= time_ms:
            break
    return beats


def ms_at_beat(beat: float, tempo_map: Sequence[TempoPoint]) -> int:
    """Convert a beat position to an absolute timestamp through a tempo map."""
    if not tempo_map or tempo_map[0].time_ms != 0:
        raise ValueError("tempo_map must start at 0 ms")
    if beat < 0:
        return round(beat * (60_000 / tempo_map[0].bpm))
    remaining = beat
    for index, point in enumerate(tempo_map):
        milliseconds_per_beat = 60_000 / point.bpm
        if index + 1 >= len(tempo_map):
            return round(point.time_ms + remaining * milliseconds_per_beat)
        next_point = tempo_map[index + 1]
        segment_beats = (next_point.time_ms - point.time_ms) / milliseconds_per_beat
        if remaining <= segment_beats:
            return round(point.time_ms + remaining * milliseconds_per_beat)
        remaining -= segment_beats
    raise AssertionError("tempo map conversion did not return")


def normalize_tempo_map(points: Sequence[TempoPoint]) -> list[TempoPoint]:
    ordered = sorted(points, key=lambda point: point.time_ms)
    if not ordered or ordered[0].time_ms != 0:
        raise ValueError("tempo_map must contain a point at 0 ms")
    if any(
        left.time_ms == right.time_ms
        for left, right in zip(ordered, ordered[1:], strict=False)
    ):
        raise ValueError("tempo_map cannot contain duplicate timestamps")
    return ordered
