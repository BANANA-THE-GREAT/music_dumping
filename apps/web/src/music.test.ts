import { describe, expect, it } from "vitest";
import {
  cleanAndQuantize,
  demoNotes,
  displayQuantizedNotes,
  toAbc,
} from "./music";

describe("score pipeline", () => {
  it("maps a C major demo to numbered notation degrees", () => {
    const notes = cleanAndQuantize(demoNotes(), 120);
    expect(notes.slice(0, 4).map((n) => n.degree)).toEqual([1, 1, 5, 5]);
    expect(notes.every((n) => n.durationBeats >= 0.25)).toBe(true);
  });
  it("creates a valid ABC header and pitches", () => {
    const abc = toAbc(cleanAndQuantize(demoNotes(), 120), 120);
    expect(abc).toContain("M:4/4");
    expect(abc).toContain("Q:1/4=120");
    expect(abc).toContain("C");
  });
  it("writes compound meter with an eighth-note denominator", () => {
    const abc = toAbc(cleanAndQuantize(demoNotes(), 120), 120, 6, 8, "C");
    expect(abc).toContain("M:6/8");
  });
  it("renders every authoritative project note without local overlap filtering", () => {
    const projectNotes = [
      {
        pitch_midi: 60,
        confidence: 0.9,
        quantized_start: 0,
        quantized_duration: 2,
      },
      {
        pitch_midi: 62,
        confidence: 0.9,
        quantized_start: 1,
        quantized_duration: 1,
      },
    ];
    expect(displayQuantizedNotes(projectNotes, 120)).toHaveLength(2);
  });
});
