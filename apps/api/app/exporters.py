import math
import struct
from collections.abc import Iterable
from typing import cast
from xml.etree.ElementTree import Element, SubElement, tostring

from app.schemas import ScoreNote, ScoreProject

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


def project_to_midi(project: ScoreProject) -> bytes:
    tempo = project.analysis.tempo_map[0].bpm
    meter = project.analysis.meter_map[0]
    microseconds = round(60_000_000 / tempo)
    denominator_power = int(math.log2(meter.denominator))
    track = bytearray()
    track.extend(b"\x00\xff\x51\x03" + microseconds.to_bytes(3, "big"))
    track.extend(b"\x00\xff\x58\x04" + bytes((meter.numerator, denominator_power, 24, 8)))
    previous_tick = 0
    for tick, _, message in _midi_events(project.notes):
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


def project_to_musicxml(project: ScoreProject) -> bytes:
    root = Element("score-partwise", version="4.0")
    work = SubElement(root, "work")
    SubElement(work, "work-title").text = project.source.file_name
    part_list = SubElement(root, "part-list")
    score_part = SubElement(part_list, "score-part", id="P1")
    SubElement(score_part, "part-name").text = "Melody"
    part = SubElement(root, "part", id="P1")
    measure = SubElement(part, "measure", number="1")
    attributes = SubElement(measure, "attributes")
    SubElement(attributes, "divisions").text = str(DIVISIONS)
    key = SubElement(attributes, "key")
    SubElement(key, "fifths").text = "0"
    time = SubElement(attributes, "time")
    meter = project.analysis.meter_map[0]
    SubElement(time, "beats").text = str(meter.numerator)
    SubElement(time, "beat-type").text = str(meter.denominator)
    clef = SubElement(attributes, "clef")
    SubElement(clef, "sign").text = "G"
    SubElement(clef, "line").text = "2"
    direction = SubElement(measure, "direction", placement="above")
    sound = SubElement(direction, "sound")
    sound.set("tempo", str(project.analysis.tempo_map[0].bpm))

    cursor = 0.0
    for score_note in sorted(project.notes, key=lambda note: note.quantized_start):
        gap = score_note.quantized_start - cursor
        if gap > 0:
            rest = SubElement(measure, "note")
            SubElement(rest, "rest")
            SubElement(rest, "duration").text = str(max(1, round(gap * DIVISIONS)))
        note = SubElement(measure, "note")
        _append_pitch(note, score_note.pitch_midi)
        SubElement(note, "duration").text = str(
            max(1, round(score_note.quantized_duration * DIVISIONS))
        )
        cursor = max(cursor, score_note.quantized_start + score_note.quantized_duration)
    xml = cast(bytes, tostring(root, encoding="utf-8"))
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + xml
