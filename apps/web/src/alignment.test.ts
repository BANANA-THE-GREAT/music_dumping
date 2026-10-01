import { describe, expect, it } from "vitest";
import { estimateGlobalOffset } from "./alignment";

describe("global audio alignment", () => {
  it("finds a bounded fixed offset without time warping", () => {
    const result = estimateGlobalOffset([0.5, 1.5, 2.5], [0.8, 1.8, 2.8]);
    expect(result.offsetSeconds).toBeCloseTo(0.3, 1);
    expect(result.matchedCount).toBe(3);
    expect(result.confidence).toBe(1);
  });

  it("returns an unconfident zero result when evidence is missing", () => {
    expect(estimateGlobalOffset([], [1])).toEqual({
      offsetSeconds: 0,
      confidence: 0,
      matchedCount: 0,
    });
  });
});
