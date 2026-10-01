from xml.etree.ElementTree import fromstring

from app.exporters import (
    DIVISIONS,
    TICKS_PER_QUARTER,
    _performance_midi_events,
    project_to_musicxml,
)
from app.schemas import (
    Analysis,
    KeyPoint,
    MeterPoint,
    PerformanceNote,
    ScoreNote,
    ScoreProject,
    SourceAudio,
    TempoPoint,
)


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


def test_performance_midi_uses_piecewise_tempo_map() -> None:
    note = PerformanceNote(
        id="tempo-note",
        source_start_ms=1_250,
        source_end_ms=1_750,
        pitch_midi=60,
        confidence=0.9,
        origin="model",
    )
    events = _performance_midi_events(
        [note],
        tempo_map=[
            TempoPoint(time_ms=0, bpm=120),
            TempoPoint(time_ms=1_000, bpm=60),
        ],
    )
    assert events[0][0] == round(2.25 * TICKS_PER_QUARTER)
    assert events[1][0] == round(2.75 * TICKS_PER_QUARTER)


def test_musicxml_preserves_tuplets_ties_chords_and_tempo_map() -> None:
    project = ScoreProject(
        project_id="rendering-fixture",
        score_name="复杂节奏样例",
        source=SourceAudio(
            file_name="fixture.wav",
            duration_ms=4000,
            audio_object_key="fixtures/fixture.wav",
        ),
        analysis=Analysis(
            tempo_map=[
                TempoPoint(time_ms=0, bpm=120),
                TempoPoint(time_ms=1000, bpm=90),
            ],
            meter_map=[MeterPoint(beat=0, numerator=4, denominator=4)],
            key_map=[KeyPoint(beat=0, tonic=0, mode="major")],
            confidence={},
        ),
        notes=[
            ScoreNote(
                id="triplet 1",
                source_start_ms=0,
                source_end_ms=167,
                pitch_midi=60,
                confidence=0.9,
                quantized_start=0,
                quantized_duration=1 / 3,
                origin="model",
            ),
            ScoreNote(
                id="chord-note",
                source_start_ms=0,
                source_end_ms=167,
                pitch_midi=64,
                confidence=0.9,
                quantized_start=0,
                quantized_duration=1 / 3,
                origin="model",
            ),
            ScoreNote(
                id="cross-measure",
                source_start_ms=1750,
                source_end_ms=2750,
                pitch_midi=67,
                confidence=0.9,
                quantized_start=3.5,
                quantized_duration=2,
                origin="model",
            ),
        ],
        pipeline=[],
        revision=1,
    )

    root = fromstring(project_to_musicxml(project).split(b"\n", 1)[1])
    assert root.findtext("./work/work-title") == "复杂节奏样例"
    assert root.findtext("./part/measure/attributes/divisions") == str(DIVISIONS)
    triplet = root.find(".//note[@id='vss-triplet-1-segment-0']")
    assert triplet is not None
    assert triplet.findtext("duration") == "8"
    assert triplet.findtext("type") == "eighth"
    assert triplet.findtext("time-modification/actual-notes") == "3"
    same_start = [
        root.find(".//note[@id='vss-chord-note-segment-0']"),
        root.find(".//note[@id='vss-triplet-1-segment-0']"),
    ]
    assert sum(note is not None and note.find("chord") is not None for note in same_start) == 1
    tied = [note for note in root.findall(".//note") if note.find("notations/tied") is not None]
    assert len(tied) == 2
    assert [sound.attrib["tempo"] for sound in root.findall(".//direction/sound")] == [
        "120",
        "90",
    ]
    assert root.findtext(".//direction[offset]/offset") == "48"
