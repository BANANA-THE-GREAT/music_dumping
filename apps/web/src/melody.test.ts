import { describe, it, expect } from "vitest";
import { refineLocalMelody } from "./melody";
import type { RawNote } from "./types";
const n = (
  pitchMidi: number,
  startTimeSeconds: number,
  durationSeconds: number,
  amplitude = 0.9,
): RawNote => ({ pitchMidi, startTimeSeconds, durationSeconds, amplitude });
const options = { mode: "balanced" as const, low_pitch: 48, high_pitch: 84 };
describe("local melody refinement", () => {
  it("tracks the confident line and keeps raw data unchanged", () => {
    const raw = [n(60, 0, 0.5), n(62, 0.5, 0.5), n(80, 0, 1, 0.3)];
    expect(refineLocalMelody(raw, options).map((n) => n.pitchMidi)).toEqual([
      60, 62,
    ]);
    expect(refineLocalMelody(raw, { ...options, mode: "raw" })).toEqual(raw);
  });
  it("stitches tiny fragments but keeps repeated notes and breaths", () => {
    expect(
      refineLocalMelody([n(60, 0, 0.3), n(60, 0.34, 0.1)], options),
    ).toHaveLength(1);
    expect(
      refineLocalMelody([n(60, 0, 0.4), n(60, 0.45, 0.4)], options),
    ).toHaveLength(2);
    expect(
      refineLocalMelody([n(60, 0, 0.1), n(60, 0.5, 0.1)], options),
    ).toHaveLength(2);
  });
});
