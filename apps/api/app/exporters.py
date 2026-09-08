import math
import struct
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, cast
from xml.etree.ElementTree import Element, SubElement, tostring

from app.schemas import PerformanceNote, ScoreNote, ScoreProject

TICKS_PER_QUARTER = 480
DIVISIONS = 8
PITCH_NAMES = (
    ("C", 0),
    ("C", 1),
    ("D", 0),
    ("D", 1),
    ("E", 0),
    ("F", 0),
    ("F", 1),
    ("G", 0),
    ("G", 1),
    ("A", 0),
    ("A", 1),
    ("B", 0),
)


def _variable_length(value: int) -> bytes:
    buffer = value & 0x7F
    encoded = bytearray([buffer])
    while value := value >> 7:
        buffer = (value & 0x7F) | 0x80
        encoded.insert(0, buffer)
    return bytes(encoded)


def _midi_events(notes: Iterable[ScoreNote]) -> list[tuple[int, int, bytes]]:
    events: list[tuple[int, int, bytes]] = []
    for note in notes:
        start = round(note.quantized_start * TICKS_PER_QUARTER)
        end = start + max(1, round(note.quantized_duration * TICKS_PER_QUARTER))
        events.append((start, 1, bytes((0x90, note.pitch_midi, 96))))
        events.append((end, 0, bytes((0x80, note.pitch_midi, 0))))
    return sorted(events)


def _pitch_bend_message(cents: float) -> bytes:
    value = max(0, min(16_383, 8_192 + round((cents / 200) * 8_191)))
    return bytes((0xE0, value & 0x7F, value >> 7))


def _performance_midi_events(
    notes: Iterable[PerformanceNote], milliseconds_per_beat: float
) -> list[tuple[int, int, bytes]]:
    events: list[tuple[int, int, bytes]] = []
    for note in notes:
        start = round(note.source_start_ms / milliseconds_per_beat * TICKS_PER_QUARTER)
        end = max(
            start + 1,
            round(note.source_end_ms / milliseconds_per_beat * TICKS_PER_QUARTER),
        )
        events.append((start, 3, bytes((0x90, note.pitch_midi, 96))))
        for bend in note.pitch_bends:
            tick = min(
                end,
                start + round(bend.offset_ms / milliseconds_per_beat * TICKS_PER_QUARTER),
            )
            events.append((tick, 2, _pitch_bend_message(bend.cents)))
        events.append((end, 0, bytes((0x80, note.pitch_midi, 0))))
        if note.pitch_bends:
            events.append((end, 1, _pitch_bend_message(0)))
    return sorted(events)


def project_to_midi(
    project: ScoreProject, version: Literal["score", "performance"] = "score"
) -> bytes:
    tempo = project.analysis.tempo_map[0].bpm
    meter = project.analysis.meter_map[0]
    microseconds = round(60_000_000 / tempo)
    denominator_power = int(math.log2(meter.denominator))
    track = bytearray()
    track.extend(b"\x00\xff\x51\x03" + microseconds.to_bytes(3, "big"))
    track.extend(b"\x00\xff\x58\x04" + bytes((meter.numerator, denominator_power, 24, 8)))
    previous_tick = 0
    milliseconds_per_beat = 60_000 / tempo
    events = (
        _performance_midi_events(project.performance_notes or [], milliseconds_per_beat)
        if version == "performance"
        else _midi_events(project.notes)
    )
    for tick, _, message in events:
        track.extend(_variable_length(tick - previous_tick))
        track.extend(message)
        previous_tick = tick
    track.extend(b"\x00\xff\x2f\x00")
    header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, TICKS_PER_QUARTER)
    return header + b"MTrk" + struct.pack(">I", len(track)) + bytes(track)


def _append_pitch(parent: Element, midi: int) -> None:
    pitch = SubElement(parent, "pitch")
    step, alter = PITCH_NAMES[midi % 12]
    SubElement(pitch, "step").text = step
    if alter:
        SubElement(pitch, "alter").text = str(alter)
    SubElement(pitch, "octave").text = str(midi // 12 - 1)


@dataclass(frozen=True)
class XmlSegment:
    measure: int
    offset: float
    duration: float
    pitch_midi: int
    tie_stop: bool
    tie_start: bool


def _key_fifths(project: ScoreProject) -> int:
    key = project.analysis.key_map[0]
    major_tonic = (key.tonic + 3) % 12 if key.mode == "minor" else key.tonic
    circle = (0, 7, 2, 9, 4, 11, 6, 1, 8, 3, 10, 5)
    index = circle.index(major_tonic)
    return index if index <= 6 else index - 12


def _segments(project: ScoreProject, measure_beats: float) -> list[XmlSegment]:
    result: list[XmlSegment] = []
    for note in sorted(project.notes, key=lambda item: item.quantized_start):
        start = note.quantized_start
        remaining = note.quantized_duration
        first = True
        while remaining > 1e-9:
            measure = int(start // measure_beats)
            offset = start - measure * measure_beats
            duration = min(remaining, measure_beats - offset)
            remaining -= duration
            result.append(
                XmlSegment(
                    measure=measure,
                    offset=offset,
                    duration=duration,
                    pitch_midi=note.pitch_midi,
                    tie_stop=not first,
                    tie_start=remaining > 1e-9,
                )
            )
            start += duration
            first = False
    return result


def _append_note(parent: Element, segment: XmlSegment) -> None:
    note = SubElement(parent, "note")
    _append_pitch(note, segment.pitch_midi)
    SubElement(note, "duration").text = str(max(1, round(segment.duration * DIVISIONS)))
    if segment.tie_stop:
        SubElement(note, "tie", type="stop")
    if segment.tie_start:
        SubElement(note, "tie", type="start")


def _append_rest(parent: Element, duration: float) -> None:
    note = SubElement(parent, "note")
    SubElement(note, "rest")
    SubElement(note, "duration").text = str(max(1, round(duration * DIVISIONS)))


def project_to_musicxml(project: ScoreProject) -> bytes:
    root = Element("score-partwise", version="4.0")
    work = SubElement(root, "work")
    SubElement(work, "work-title").text = project.source.file_name
    part_list = SubElement(root, "part-list")
    score_part = SubElement(part_list, "score-part", id="P1")
    SubElement(score_part, "part-name").text = "Melody"
    part = SubElement(root, "part", id="P1")
    meter = project.analysis.meter_map[0]
    measure_beats = meter.numerator * 4 / meter.denominator
    segments = _segments(project, measure_beats)
    last_measure = max((segment.measure for segment in segments), default=0)
    by_measure = {
        index: [segment for segment in segments if segment.measure == index]
        for index in range(last_measure + 1)
    }
    for measure_index in range(last_measure + 1):
        measure = SubElement(part, "measure", number=str(measure_index + 1))
        if measure_index == 0:
            attributes = SubElement(measure, "attributes")
            SubElement(attributes, "divisions").text = str(DIVISIONS)
            key = SubElement(attributes, "key")
            SubElement(key, "fifths").text = str(_key_fifths(project))
            time = SubElement(attributes, "time")
            SubElement(time, "beats").text = str(meter.numerator)
            SubElement(time, "beat-type").text = str(meter.denominator)
            clef = SubElement(attributes, "clef")
            SubElement(clef, "sign").text = "G"
            SubElement(clef, "line").text = "2"
            direction = SubElement(measure, "direction", placement="above")
            sound = SubElement(direction, "sound")
            sound.set("tempo", str(project.analysis.tempo_map[0].bpm))
        cursor = 0.0
        for segment in by_measure[measure_index]:
            if segment.offset > cursor:
                _append_rest(measure, segment.offset - cursor)
            _append_note(measure, segment)
            cursor = max(cursor, segment.offset + segment.duration)
        if cursor < measure_beats:
            _append_rest(measure, measure_beats - cursor)
    xml = cast(bytes, tostring(root, encoding="utf-8"))
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + xml
