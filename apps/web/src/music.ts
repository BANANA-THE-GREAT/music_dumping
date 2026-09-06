import type { RawNote, ScoreNote } from "./types";
import { scoreMeasures } from "./notation";

const MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11];
const MINOR_SCALE = [0, 2, 3, 5, 7, 8, 10];
const PITCH_NAMES = [
  "C",
  "^C",
  "D",
  "^D",
  "E",
  "F",
  "^F",
  "G",
  "^G",
  "A",
  "^A",
  "B",
];

function decorateNote(
  note: RawNote,
  id: number,
  startBeat: number,
  durationBeats: number,
  keyMidi: number,
  mode: "major" | "minor",
): ScoreNote {
  const relative = note.pitchMidi - keyMidi;
  const octave = Math.floor(relative / 12);
  const pc = ((relative % 12) + 12) % 12;
  let degreeIndex = 0;
  let accidental = 99;
  const scale = mode === "major" ? MAJOR_SCALE : MINOR_SCALE;
  scale.forEach((value, index) => {
    const difference = pc - value;
    if (Math.abs(difference) < Math.abs(accidental)) {
      degreeIndex = index;
      accidental = difference;
    }
  });
  return {
    ...note,
    id,
    startBeat,
    durationBeats,
    degree: degreeIndex + 1,
    accidental,
    octave,
  };
}

export function displayQuantizedNotes(
  notes: Array<{
    pitch_midi: number;
    confidence: number;
    quantized_start: number;
    quantized_duration: number;
  }>,
  bpm: number,
  keyMidi = 60,
  mode: "major" | "minor" = "major",
): ScoreNote[] {
  const secondsPerBeat = 60 / bpm;
  return notes.map((note, id) =>
    decorateNote(
      {
        pitchMidi: note.pitch_midi,
        amplitude: note.confidence,
        startTimeSeconds: note.quantized_start * secondsPerBeat,
        durationSeconds: note.quantized_duration * secondsPerBeat,
      },
      id,
      note.quantized_start,
      note.quantized_duration,
      keyMidi,
      mode,
    ),
  );
}

export function cleanAndQuantize(
  raw: RawNote[],
  bpm: number,
  keyMidi = 60,
  mode: "major" | "minor" = "major",
): ScoreNote[] {
  const secondsPerBeat = 60 / bpm;
  const filtered = raw
    .filter(
      (n) =>
        n.durationSeconds >= 0.09 &&
        n.amplitude >= 0.18 &&
        n.pitchMidi >= 45 &&
        n.pitchMidi <= 84,
    )
    .sort(
      (a, b) =>
        a.startTimeSeconds - b.startTimeSeconds || b.amplitude - a.amplitude,
    );

  const monophonic: RawNote[] = [];
  for (const note of filtered) {
    const previous = monophonic.at(-1);
    if (
      previous &&
      note.startTimeSeconds <
        previous.startTimeSeconds + previous.durationSeconds
    ) {
      if (note.amplitude > previous.amplitude * 1.12) {
        previous.durationSeconds = Math.max(
          0.08,
          note.startTimeSeconds - previous.startTimeSeconds,
        );
        monophonic.push({ ...note });
      }
      continue;
    }
    monophonic.push({ ...note });
  }

  return monophonic.map((note, id) => {
    const startBeat =
      Math.round((note.startTimeSeconds / secondsPerBeat) * 4) / 4;
    const durationBeats = Math.max(
      0.25,
      Math.round((note.durationSeconds / secondsPerBeat) * 4) / 4,
    );
    return decorateNote(note, id, startBeat, durationBeats, keyMidi, mode);
  });
}

function abcPitch(midi: number): string {
  const octave = Math.floor(midi / 12) - 1;
  let name = PITCH_NAMES[((midi % 12) + 12) % 12];
  if (!name.startsWith("^")) name = "=" + name;
  if (octave >= 5) name = name.toLowerCase() + "'".repeat(octave - 5);
  else if (octave < 4) name += ",".repeat(4 - octave);
  return name;
}

function abcLength(beats: number): string {
  const units = Math.max(1, Math.round(beats * 8));
  return units === 4 ? "" : `${units}/4`;
}

export function toAbc(
  notes: ScoreNote[],
  bpm: number,
  meter: 2 | 3 | 4 | 6 = 4,
  denominator: 4 | 8 = 4,
  key = "C",
): string {
  return mappedAbc(notes, bpm, meter, denominator, key).abc;
}

export function mappedAbc(
  notes: ScoreNote[],
  bpm: number,
  meter: 2 | 3 | 4 | 6 = 4,
  denominator: 4 | 8 = 4,
  key = "C",
) {
  let abc = `X:1\nT:人声转录结果\nM:${meter}/${denominator}\nL:1/8\nQ:1/4=${bpm}\nK:${key}\n`;
  const mapping: Array<{ offset: number; index: number }> = [];
  for (const measure of scoreMeasures(notes, (meter * 4) / denominator)) {
    for (const segment of measure) {
      if (segment.index !== null)
        mapping.push({ offset: abc.length, index: segment.index });
      abc += `${segment.index === null ? "z" : abcPitch(notes[segment.index].pitchMidi)}${abcLength(segment.duration)}${segment.index !== null && segment.continues ? "-" : ""} `;
    }
    abc += "| ";
  }
  return { abc: abc + (notes.length ? "]" : "z8 |]"), mapping };
}

export function demoNotes(): RawNote[] {
  const pitches = [60, 60, 67, 67, 69, 69, 67, 65, 65, 64, 64, 62, 62, 60];
  let cursor = 0;
  return pitches.map((pitchMidi, i) => {
    const durationSeconds = i === 6 || i === 13 ? 0.92 : 0.44;
    const note = {
      pitchMidi,
      amplitude: 0.82,
      startTimeSeconds: cursor,
      durationSeconds,
    };
    cursor += i === 6 || i === 13 ? 1 : 0.5;
    return note;
  });
}
