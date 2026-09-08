from app.exporters import TICKS_PER_QUARTER, _performance_midi_events
from app.schemas import PerformanceNote


def test_performance_midi_uses_source_timing_and_pitch_bends() -> None:
    note = PerformanceNote(
        id="performance-1",
        source_start_ms=250,
        source_end_ms=750,
        pitch_midi=69,
        confidence=0.9,
        origin="model",
        pitch_bends=[{"offset_ms": 100, "cents": 50}],
    )

    events = _performance_midi_events([note], milliseconds_per_beat=500)

    assert events[0] == (TICKS_PER_QUARTER // 2, 3, bytes((0x90, 69, 96)))
    assert events[1][0] == round(0.7 * TICKS_PER_QUARTER)
    assert events[1][2][0] == 0xE0
    assert events[-2] == (round(1.5 * TICKS_PER_QUARTER), 0, bytes((0x80, 69, 0)))
    assert events[-1][2] == bytes((0xE0, 0, 64))


def test_performance_midi_resets_bend_before_an_adjacent_note() -> None:
    left = PerformanceNote(
        id="left",
        source_start_ms=0,
        source_end_ms=500,
        pitch_midi=69,
        confidence=0.9,
        origin="model",
        pitch_bends=[{"offset_ms": 100, "cents": 50}],
    )
    right = PerformanceNote(
        id="right",
        source_start_ms=500,
        source_end_ms=1000,
        pitch_midi=71,
        confidence=0.9,
        origin="model",
        pitch_bends=[{"offset_ms": 0, "cents": -25}],
    )

    boundary = [
        event
        for event in _performance_midi_events([left, right], 500)
        if event[0] == TICKS_PER_QUARTER
    ]

    assert [event[1] for event in boundary] == [0, 1, 2, 3]
