import { describe, expect, it } from "vitest";
import { pianoRollLayout, pianoRollMetrics, renderPianoRoll } from "./piano-roll";
import type { ScoreNote } from "./types";

const notes: ScoreNote[] = [
  {
    id: 0,
    pitchMidi: 60,
    amplitude: 0.9,
    startTimeSeconds: 0,
    durationSeconds: 0.5,
    startBeat: 0,
    durationBeats: 1,
    degree: 1,
    accidental: 0,
    octave: 0,
  },
  {
    id: 1,
    pitchMidi: 64,
    amplitude: 0.8,
    startTimeSeconds: 0.5,
    durationSeconds: 1,
    startBeat: 1,
    durationBeats: 2,
    degree: 3,
    accidental: 0,
    octave: 0,
  },
];

describe("piano roll", () => {
  it("maps beat and pitch coordinates into the viewport", () => {
    const layout = pianoRollLayout(notes, 400, 140);
    expect(layout[0].x).toBe(0);
    expect(layout[1].x).toBe(100);
    expect(layout[1].width).toBe(200);
    expect(layout[1].y).toBeLessThan(layout[0].y);
  });

  it("renders selectable note rectangles", () => {
    const svg = renderPianoRoll(notes, 1);
    expect(svg).toContain('data-note="1"');
    expect(svg).toContain("roll-note selected");
  });

  it("renders explicit rest regions", () => {
    const svg = renderPianoRoll(
      [{ ...notes[0], startBeat: 1 }],
      null,
    );
    expect(svg).toContain('class="roll-rest"');
    expect(svg).toContain('data-rest-start="0"');
  });

  it("exposes stable beat and pitch bounds for pointer editing", () => {
    expect(pianoRollMetrics(notes)).toEqual({ endBeat: 4, lowPitch: 58, highPitch: 66 });
  });

  it("overlays voiced F0 and reviewed boundary evidence", () => {
    const svg = renderPianoRoll(notes, null, 400, 140, {
      bpm: 120,
      frames: [
        { time_seconds: 0, f0_hz: 261.63, periodicity: 0.9 },
        { time_seconds: 0.01, f0_hz: 262, periodicity: 0.8 },
        { time_seconds: 0.02, f0_hz: 262, periodicity: 0.1 },
      ],
      boundaries: [
        {
          noteIndex: 0,
          originalEndSeconds: 0.5,
          proposedEndSeconds: 0.57,
          status: "pending",
        },
      ],
      performanceNotes: [
        { startSeconds: 0.07, endSeconds: 0.46, pitchMidi: 60 },
      ],
      conflictNoteIndices: [0],
    });
    expect(svg).toContain('class="f0-track"');
    expect(svg).toContain('class="boundary-guide pending"');
    expect(svg).toContain('class="performance-note"');
    expect(svg).toContain("roll-note conflict");
  });
});
