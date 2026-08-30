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
): string {
  const rectangles = pianoRollLayout(notes, width, height);
  const { endBeat } = pianoRollMetrics(notes);
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
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="钢琴卷帘">${beatLines}${noteRects}</svg>`;
}
