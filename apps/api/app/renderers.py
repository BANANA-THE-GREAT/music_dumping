from __future__ import annotations

from html import escape
from math import isclose, log2

from app.schemas import MeterPoint, ScoreNote, ScoreProject

PAGE_WIDTH = 1400
PAGE_HEIGHT = 900
STAFF_TOP = 170
STAFF_GAP = 58
STAFF_LINE_GAP = 12
MEASURES_PER_SYSTEM = 4
BEATS_PER_MEASURE_DEFAULT = 4.0
JIANPU_WIDTH = 1400
JIANPU_LEFT = 80
JIANPU_TOP = 150
JIANPU_LINE_HEIGHT = 150


def _meter_at(project: ScoreProject, beat: float) -> MeterPoint:
    points = [point for point in project.analysis.meter_map if point.beat <= beat]
    return max(points, key=lambda point: point.beat) if points else MeterPoint(
        beat=0, numerator=4, denominator=4
    )


def _beat_measure_info(project: ScoreProject, beat: float) -> tuple[int, float, float]:
    meter = _meter_at(project, beat)
    beats_per_measure = meter.numerator * 4 / meter.denominator
    measure = int(beat // beats_per_measure)
    offset = beat - measure * beats_per_measure
    return measure, offset, beats_per_measure


def _pitch_y(pitch_midi: int, top: float) -> float:
    # The middle staff line is B4 (MIDI 71). Ledger lines are added below.
    return top + 2 * STAFF_LINE_GAP - (pitch_midi - 71) * (STAFF_LINE_GAP / 2)


def _note_name(pitch_midi: int) -> tuple[str, int]:
    names = ("C", "C", "D", "D", "E", "F", "F", "G", "G", "A", "A", "B")
    alters = (0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0)
    index = pitch_midi % 12
    return names[index], alters[index]


def _svg_text(x: float, y: float, text: str, size: int, *, anchor: str = "middle") -> str:
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-family="serif" font-size="{size}px" '
        f'text-anchor="{anchor}">{escape(text)}</text>'
    )


def _ledger_lines(pitch_midi: int, x: float, top: float) -> str:
    y = _pitch_y(pitch_midi, top)
    lines: list[str] = []
    if y < top:
        current = top - STAFF_LINE_GAP
        while current >= y - 1:
            lines.append(
                f'<line x1="{x - 16:.2f}" y1="{current:.2f}" '
                f'x2="{x + 16:.2f}" y2="{current:.2f}" />'
            )
            current -= STAFF_LINE_GAP
    if y > top + 4 * STAFF_LINE_GAP:
        current = top + 5 * STAFF_LINE_GAP
        while current <= y + 1:
            lines.append(
                f'<line x1="{x - 16:.2f}" y1="{current:.2f}" '
                f'x2="{x + 16:.2f}" y2="{current:.2f}" />'
            )
            current += STAFF_LINE_GAP
    return "".join(lines)


def _draw_note(note: ScoreNote, x: float, top: float, duration_beats: float) -> str:
    y = _pitch_y(note.pitch_midi, top)
    name, alter = _note_name(note.pitch_midi)
    accidental = "♯" if alter else ""
    filled = duration_beats < 2
    rx, ry = 9, 6
    notehead = (
        f'<ellipse cx="{x:.2f}" cy="{y:.2f}" rx="{rx}" ry="{ry}" '
        f'transform="rotate(-20 {x:.2f} {y:.2f})" class="notehead" />'
        if filled
        else f'<ellipse cx="{x:.2f}" cy="{y:.2f}" rx="{rx}" ry="{ry}" '
        f'fill="white" transform="rotate(-20 {x:.2f} {y:.2f})" class="notehead" />'
    )
    stem_x = x + 8 if note.pitch_midi < 71 else x - 8
    stem_end = y - 42 if note.pitch_midi < 71 else y + 42
    stem = (
        f'<line x1="{stem_x:.2f}" y1="{y:.2f}" '
        f'x2="{stem_x:.2f}" y2="{stem_end:.2f}" class="stem" />'
    )
    source_ids = escape(",".join(note.source_note_ids))
    return (
        f'<g data-note-id="{escape(note.id)}" data-source-note-ids="{source_ids}">'
        f'{_ledger_lines(note.pitch_midi, x, top)}'
        f'{_svg_text(x - 18 if alter else x, y + 5, accidental, 20)}'
        f'{notehead}{stem}</g>'
    )


def render_staff_svg(project: ScoreProject) -> bytes:
    notes = sorted(project.notes, key=lambda note: (note.quantized_start, note.id))
    last_beat = max(
        (note.quantized_start + note.quantized_duration for note in notes),
        default=BEATS_PER_MEASURE_DEFAULT,
    )
    meter = _meter_at(project, 0)
    beats_per_measure = meter.numerator * 4 / meter.denominator
    measure_count = max(1, int((last_beat + beats_per_measure - 1e-9) // beats_per_measure) + 1)
    system_count = (measure_count + MEASURES_PER_SYSTEM - 1) // MEASURES_PER_SYSTEM
    system_height = 230
    height = max(PAGE_HEIGHT, 150 + system_count * system_height)
    content: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{PAGE_WIDTH}" height="{height}" '
        f'viewBox="0 0 {PAGE_WIDTH} {height}" role="img" aria-label="五线谱">',
        '<style>.staff{stroke:#201d19;stroke-width:1}.bar{stroke:#201d19;stroke-width:1.5}.notehead{fill:#201d19;stroke:#201d19;stroke-width:1}.stem{stroke:#201d19;stroke-width:1.5}.title{font-family:serif;font-size:26px;font-weight:700}.meta{font-family:sans-serif;font-size:14px;fill:#5f584e}</style>',
        _svg_text(PAGE_WIDTH / 2, 48, project.score_name or project.source.file_name, 26),
        _svg_text(PAGE_WIDTH / 2, 76, "五线谱 · 谱面版", 14),
    ]
    notes_by_measure: dict[int, list[ScoreNote]] = {}
    for note in notes:
        measure, _, _ = _beat_measure_info(project, note.quantized_start)
        notes_by_measure.setdefault(measure, []).append(note)
    for system in range(system_count):
        top = STAFF_TOP + system * system_height
        first_measure = system * MEASURES_PER_SYSTEM
        last_measure = min(measure_count, first_measure + MEASURES_PER_SYSTEM)
        system_width = PAGE_WIDTH - 150
        measure_width = system_width / max(1, last_measure - first_measure)
        content.append(f'<g data-system="{system + 1}">')
        for line in range(5):
            y = top + line * STAFF_LINE_GAP
            content.append(
                f'<line x1="90" y1="{y:.2f}" x2="{PAGE_WIDTH - 60}" '
                f'y2="{y:.2f}" class="staff" />'
            )
        content.append(_svg_text(105, top + 38, "𝄞", 42))
        content.append(_svg_text(132, top - 12, f"{meter.numerator}/{meter.denominator}", 16))
        for measure in range(first_measure, last_measure + 1):
            x = 150 + (measure - first_measure) * measure_width
            content.append(
                f'<line x1="{x:.2f}" y1="{top - 4}" x2="{x:.2f}" '
                f'y2="{top + 4 * STAFF_LINE_GAP + 4}" class="bar" />'
            )
        for measure in range(first_measure, last_measure):
            left = 150 + (measure - first_measure) * measure_width
            for note in notes_by_measure.get(measure, []):
                offset = note.quantized_start - measure * beats_per_measure
                x = left + (offset / beats_per_measure) * measure_width
                content.append(_draw_note(note, x, top, note.quantized_duration))
        content.append(_svg_text(80, top + 4 * STAFF_LINE_GAP + 28, str(system + 1), 12))
        content.append("</g>")
    content.append("</svg>")
    return "".join(content).encode("utf-8")


def _jianpu_pitch(pitch_midi: int, project: ScoreProject) -> tuple[int, int, int]:
    key = project.analysis.key_map[0] if project.analysis.key_map else None
    tonic = key.tonic if key else 0
    mode = key.mode if key else "major"
    intervals = (0, 2, 4, 5, 7, 9, 11) if mode == "major" else (0, 2, 3, 5, 7, 8, 10)
    relative = (pitch_midi - tonic) % 12
    degree_index = min(range(7), key=lambda index: abs(intervals[index] - relative))
    accidental = relative - intervals[degree_index]
    if accidental > 6:
        accidental -= 12
    if accidental < -6:
        accidental += 12
    reference_tonic = 60 + tonic
    octave = (pitch_midi - reference_tonic - intervals[degree_index]) // 12
    return degree_index + 1, octave, accidental


def _jianpu_note_text(project: ScoreProject, note: ScoreNote) -> tuple[str, int, int]:
    degree, octave, accidental = _jianpu_pitch(note.pitch_midi, project)
    prefix = "♯" if accidental > 0 else "♭" if accidental < 0 else ""
    return f"{prefix}{degree}", octave, accidental


def _duration_marks(duration: float) -> tuple[int, int]:
    """Return the number of Jianpu underlines and augmentation dots."""
    if duration <= 0:
        return 0, 0
    for dots, multiplier in ((0, 1.0), (1, 1.5), (2, 1.75)):
        base = duration / multiplier
        exponent = round(log2(base))
        if isclose(base, 2**exponent, abs_tol=1e-6):
            return max(0, -exponent), dots
    return max(0, round(-log2(min(duration, 1.0)))), 0


def _rest_ranges(
    notes: list[ScoreNote], measure_start: float, measure_end: float
) -> list[tuple[float, float]]:
    occupied = sorted(
        (
            max(measure_start, note.quantized_start),
            min(measure_end, note.quantized_start + note.quantized_duration),
        )
        for note in notes
        if note.quantized_start < measure_end
        and note.quantized_start + note.quantized_duration > measure_start
    )
    rests: list[tuple[float, float]] = []
    cursor = measure_start
    for start, end in occupied:
        if start > cursor + 1e-8:
            rests.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < measure_end - 1e-8:
        rests.append((cursor, measure_end))
    return rests


def render_jianpu_svg(project: ScoreProject) -> bytes:
    notes = sorted(project.notes, key=lambda note: (note.quantized_start, note.id))
    last_beat = max(
        (note.quantized_start + note.quantized_duration for note in notes),
        default=BEATS_PER_MEASURE_DEFAULT,
    )
    meter = _meter_at(project, 0)
    beats_per_measure = meter.numerator * 4 / meter.denominator
    measure_count = max(1, int((last_beat + beats_per_measure - 1e-9) // beats_per_measure) + 1)
    measures_per_line = 4
    line_count = (measure_count + measures_per_line - 1) // measures_per_line
    height = max(500, JIANPU_TOP + line_count * JIANPU_LINE_HEIGHT + 100)
    content: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{JIANPU_WIDTH}" height="{height}" '
        f'viewBox="0 0 {JIANPU_WIDTH} {height}" role="img" aria-label="简谱">',
        '<style>'
        '.jp-number{font-family:"Noto Sans SC",sans-serif;font-size:32px;'
        'font-weight:600;fill:#201d19}.jp-octave-dot,.jp-rhythm-dot{fill:#201d19}'
        '.jp-bar{stroke:#201d19;stroke-width:1.5}.jp-rest{font-family:serif;'
        'font-size:28px;fill:#5f584e}.jp-tie{fill:none;stroke:#201d19;'
        'stroke-width:1.5}.jp-underline{stroke:#201d19;stroke-width:1.8}'
        '.jp-meta{font-family:sans-serif;font-size:15px;'
        'fill:#5f584e}</style>',
        _svg_text(JIANPU_WIDTH / 2, 45, project.score_name or project.source.file_name, 26),
        _svg_text(JIANPU_WIDTH / 2, 74, f"1 = {meter.numerator}/{meter.denominator} · 简谱版", 15),
    ]
    for line in range(line_count):
        top = JIANPU_TOP + line * JIANPU_LINE_HEIGHT
        first_measure = line * measures_per_line
        last_measure = min(measure_count, first_measure + measures_per_line)
        system_width = JIANPU_WIDTH - 2 * JIANPU_LEFT
        measure_width = system_width / max(1, last_measure - first_measure)
        content.append(f'<g data-system="{line + 1}">')
        for measure in range(first_measure, last_measure + 1):
            x = JIANPU_LEFT + (measure - first_measure) * measure_width
            content.append(
                f'<line x1="{x:.2f}" y1="{top - 36}" x2="{x:.2f}" '
                f'y2="{top + 40}" class="jp-bar" />'
            )
        for measure in range(first_measure, last_measure):
            left = JIANPU_LEFT + (measure - first_measure) * measure_width
            measure_start = measure * beats_per_measure
            measure_end = measure_start + beats_per_measure
            measure_notes = [
                note
                for note in notes
                if note.quantized_start < measure_end
                and note.quantized_start + note.quantized_duration > measure_start
            ]
            for rest_start, rest_end in _rest_ranges(notes, measure_start, measure_end):
                rest_x = left + ((rest_start - measure_start) / beats_per_measure) * measure_width
                content.append(
                    f'<g class="jp-rest-range" data-rest-start="{rest_start:.6g}" '
                    f'data-rest-end="{rest_end:.6g}">{_svg_text(rest_x, top + 10, "0", 26)}</g>'
                )
            same_start_indexes: dict[float, int] = {}
            for note in measure_notes:
                segment_start = max(note.quantized_start, measure_start)
                segment_end = min(note.quantized_start + note.quantized_duration, measure_end)
                offset = segment_start - measure_start
                start_key = round(note.quantized_start, 8)
                collision_index = same_start_indexes.get(start_key, 0)
                same_start_indexes[start_key] = collision_index + 1
                x = (
                    left
                    + (offset / beats_per_measure) * measure_width
                    + collision_index * 22
                )
                label, octave, accidental = _jianpu_note_text(project, note)
                source_ids = escape(",".join(note.source_note_ids))
                continuation = note.quantized_start < measure_start - 1e-8
                content.append(
                    f'<g data-note-id="{escape(note.id)}" '
                    f'data-source-note-ids="{source_ids}" '
                    f'data-continuation="{str(continuation).lower()}">'
                )
                if not continuation:
                    content.append(_svg_text(x, top + 10, label, 32))
                    for index in range(abs(octave)):
                        dot_y = top - 18 - index * 9 if octave > 0 else top + 34 + index * 9
                        content.append(
                            f'<circle cx="{x:.2f}" cy="{dot_y:.2f}" '
                            f'r="2.8" class="jp-octave-dot" />'
                        )
                    underlines, rhythm_dots = _duration_marks(note.quantized_duration)
                    for index in range(underlines):
                        underline_y = top + 20 + index * 6
                        content.append(
                            f'<line x1="{x - 13:.2f}" y1="{underline_y:.2f}" '
                            f'x2="{x + 13:.2f}" y2="{underline_y:.2f}" '
                            f'class="jp-underline" />'
                        )
                    for index in range(rhythm_dots):
                        content.append(
                            f'<circle cx="{x + 21 + index * 8:.2f}" cy="{top + 2:.2f}" '
                            f'r="2.8" class="jp-rhythm-dot" />'
                        )
                extension_start = x + (20 if not continuation else 4)
                extension_end = (
                    left
                    + ((segment_end - measure_start) / beats_per_measure) * measure_width
                    - 8
                )
                if (
                    continuation or note.quantized_duration > 1.0
                ) and extension_end > extension_start:
                    content.append(
                        f'<line x1="{extension_start:.2f}" y1="{top + 18}" '
                        f'x2="{extension_end:.2f}" y2="{top + 18}" class="jp-tie" />'
                    )
                content.append("</g>")
        content.append(_svg_text(45, top + 10, str(line + 1), 12))
        content.append("</g>")
    content.append("</svg>")
    return "".join(content).encode("utf-8")
