import type { F0Frame } from "@vocal-score/contracts";
import type { ScoreNote } from "./types";

export interface PianoRollRect {
  index: number;
  x: number;
  y: number;
  width: number;
  height: number;
  pitch: number;
}

export interface PianoRollMetrics {
  endBeat: number;
  lowPitch: number;
  highPitch: number;
}

export interface PianoRollBoundaryMarker {
  noteIndex: number;
  originalEndSeconds: number;
  proposedEndSeconds: number;
  status: "pending" | "accepted" | "rejected";
}

export interface PianoRollEvidence {
  bpm: number;
  frames: F0Frame[];
  boundaries: PianoRollBoundaryMarker[];
  periodicityThreshold?: number;
}

export function pianoRollMetrics(notes: ScoreNote[]): PianoRollMetrics {
  return {
    endBeat: Math.max(...notes.map((note) => note.startBeat + note.durationBeats), 4),
    lowPitch: Math.min(...notes.map((note) => note.pitchMidi), 60) - 2,
    highPitch: Math.max(...notes.map((note) => note.pitchMidi), 60) + 2,
  };
}

export function pianoRollLayout(
  notes: ScoreNote[],
  width: number,
  height: number,
): PianoRollRect[] {
  if (!notes.length) return [];
  const { endBeat, lowPitch: low, highPitch: high } = pianoRollMetrics(notes);
  const rowHeight = height / (high - low + 1);
  return notes.map((note, index) => ({
    index,
    x: (note.startBeat / endBeat) * width,
    y: (high - note.pitchMidi) * rowHeight,
    width: Math.max(3, (note.durationBeats / endBeat) * width),
    height: Math.max(3, rowHeight - 1),
    pitch: note.pitchMidi,
  }));
}

export function renderPianoRoll(
  notes: ScoreNote[],
  selectedIndex: number | null,
  width = 900,
  height = 280,
  evidence?: PianoRollEvidence,
): string {
  const rectangles = pianoRollLayout(notes, width, height);
  const { endBeat, lowPitch, highPitch } = pianoRollMetrics(notes);
  const beatLines = Array.from({ length: Math.ceil(endBeat) + 1 }, (_, beat) => {
    const x = (beat / endBeat) * width;
    return `<line x1="${x}" y1="0" x2="${x}" y2="${height}" class="${beat % 4 === 0 ? "bar" : "beat"}" />`;
  }).join("");
  const noteRects = rectangles
    .map(
      (rect) =>
        `<rect data-note="${rect.index}" x="${rect.x.toFixed(2)}" y="${rect.y.toFixed(2)}" width="${rect.width.toFixed(2)}" height="${rect.height.toFixed(2)}" class="roll-note${selectedIndex === rect.index ? " selected" : ""}"><title>MIDI ${rect.pitch}</title></rect>`,
    )
    .join("");
  const durationSeconds = (endBeat * 60) / (evidence?.bpm || 120);
  const pitchY = (pitch: number) =>
    ((highPitch - pitch + 0.5) / (highPitch - lowPitch + 1)) * height;
  const timeX = (seconds: number) =>
    Math.max(0, Math.min(width, (seconds / durationSeconds) * width));
  const threshold = evidence?.periodicityThreshold ?? 0.4;
  const f0Runs: string[][] = [];
  let currentRun: string[] = [];
  for (const frame of evidence?.frames ?? []) {
    const pitch = 69 + 12 * Math.log2(frame.f0_hz / 440);
    const visible =
      frame.periodicity >= threshold &&
      frame.time_seconds <= durationSeconds &&
      Number.isFinite(pitch) &&
      pitch >= lowPitch &&
      pitch <= highPitch;
    if (!visible) {
      if (currentRun.length > 1) f0Runs.push(currentRun);
      currentRun = [];
      continue;
    }
    currentRun.push(
      `${timeX(frame.time_seconds).toFixed(2)},${pitchY(pitch).toFixed(2)}`,
    );
  }
  if (currentRun.length > 1) f0Runs.push(currentRun);
  const f0Paths = f0Runs
    .map((points) => `<polyline class="f0-track" points="${points.join(" ")}" />`)
    .join("");
  const boundaryGuides = (evidence?.boundaries ?? [])
    .map((boundary) => {
      const note = notes[boundary.noteIndex];
      if (!note) return "";
      const y = pitchY(note.pitchMidi);
      const originalX = timeX(boundary.originalEndSeconds);
      const proposedX = timeX(boundary.proposedEndSeconds);
      return `<g class="boundary-guide ${boundary.status}"><line x1="${originalX.toFixed(2)}" y1="${y.toFixed(2)}" x2="${proposedX.toFixed(2)}" y2="${y.toFixed(2)}" /><line x1="${originalX.toFixed(2)}" y1="${(y - 7).toFixed(2)}" x2="${originalX.toFixed(2)}" y2="${(y + 7).toFixed(2)}" /><line x1="${proposedX.toFixed(2)}" y1="${(y - 9).toFixed(2)}" x2="${proposedX.toFixed(2)}" y2="${(y + 9).toFixed(2)}" /></g>`;
    })
    .join("");
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="钢琴卷帘">${beatLines}${f0Paths}${boundaryGuides}${noteRects}</svg>`;
}
