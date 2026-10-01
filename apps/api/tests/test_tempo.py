import pytest
from app.schemas import TempoPoint
from app.tempo import beat_at_ms, ms_at_beat


def test_ms_at_beat_uses_constant_tempo() -> None:
    tempo_map = [TempoPoint(time_ms=0, bpm=120)]
    assert ms_at_beat(-1, tempo_map) == -500
    assert ms_at_beat(3.5, tempo_map) == 1750


def test_ms_at_beat_uses_piecewise_tempo_map() -> None:
    tempo_map = [
        TempoPoint(time_ms=0, bpm=120),
        TempoPoint(time_ms=2000, bpm=60),
    ]
    assert ms_at_beat(4, tempo_map) == 2000
    assert ms_at_beat(5.5, tempo_map) == 3500


@pytest.mark.parametrize("time_ms", [0, 250, 1999, 2000, 2750, 5000])
def test_tempo_conversion_round_trip(time_ms: int) -> None:
    tempo_map = [
        TempoPoint(time_ms=0, bpm=120),
        TempoPoint(time_ms=2000, bpm=75),
        TempoPoint(time_ms=4400, bpm=150),
    ]
    assert ms_at_beat(beat_at_ms(time_ms, tempo_map), tempo_map) == time_ms
