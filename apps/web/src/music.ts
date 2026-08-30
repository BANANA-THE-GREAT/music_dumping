import type { RawNote, ScoreNote } from "./types";

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
    const relative = note.pitchMidi - keyMidi;
    const octave = Math.floor(relative / 12);
    const pc = ((relative % 12) + 12) % 12;
    let degreeIndex = 0;
    let accidental = 99;
    const scale = mode === "major" ? MAJOR_SCALE : MINOR_SCALE;
    scale.forEach((v, i) => {
      const diff = pc - v;
      if (Math.abs(diff) < Math.abs(accidental)) {
        degreeIndex = i;
        accidental = diff;
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
  });
}

function abcPitch(midi: number): string {
  const octave = Math.floor(midi / 12) - 1;
  let name = PITCH_NAMES[((midi % 12) + 12) % 12];
  if (octave >= 5) name = name.toLowerCase() + "'".repeat(octave - 5);
  else if (octave < 4) name += ",".repeat(4 - octave);
  return name;
}

function abcLength(beats: number): string {
  const eighths = Math.max(1, Math.round(beats * 2));
  return eighths === 1 ? "" : String(eighths);
}

export function toAbc(
  notes: ScoreNote[],
  bpm: number,
  meter: 2 | 3 | 4 | 6 = 4,
  denominator: 4 | 8 = 4,
  key = "C",
): string {
  if (!notes.length)
    return `X:1\nT:等待转录\nM:${meter}/${denominator}\nL:1/8\nK:${key}\nz8|`;
  const tokens: string[] = [];
  let cursor = 0;
  let bar = 0;
  const measureBeats = (meter * 4) / denominator;
  for (const note of notes) {
    const rest = note.startBeat - cursor;
    if (rest >= 0.24) tokens.push(`z${abcLength(rest)}`);
    while (note.startBeat >= bar + measureBeats) {
      tokens.push("|");
      bar += measureBeats;
    }
    tokens.push(`${abcPitch(note.pitchMidi)}${abcLength(note.durationBeats)}`);
    cursor = note.startBeat + note.durationBeats;
  }
  return `X:1\nT:人声转录结果\nM:${meter}/${denominator}\nL:1/8\nQ:1/4=${bpm}\nK:${key}\n${tokens.join(" ")} |]`;
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
