import { describe, expect, it } from "vitest";
import { waveformPeaks } from "./waveform";

describe("waveform peaks", () => {
  it("downsamples all channels into min/max buckets", () => {
    const peaks = waveformPeaks(
      [new Float32Array([-1, -0.5, 0.5, 1]), new Float32Array([-0.2, 0.2, -0.8, 0.8])],
      2,
    );
    expect(peaks).toEqual([
      { min: -1, max: 0.20000000298023224 },
      { min: -0.800000011920929, max: 1 },
    ]);
  });

  it("handles empty input", () => {
    expect(waveformPeaks([], 100)).toEqual([]);
  });
});
