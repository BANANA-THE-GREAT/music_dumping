import { describe, expect, it } from "vitest";
import type { BoundarySuggestion } from "@vocal-score/contracts";
import {
  boundaryDeltaLabel,
  boundaryReasonLabel,
  orderedBoundarySuggestions,
} from "./boundary-review";

const suggestion = (
  id: string,
  status: BoundarySuggestion["review_status"],
  original: number,
  proposed: number,
): BoundarySuggestion => ({
  id,
  source_note_id: `source-${id}`,
  kind: "adjust_end",
  original_end_ms: original,
  proposed_end_ms: proposed,
  confidence: 0.8,
  reason:
    proposed > original ? "f0_voicing_extension" : "f0_voicing_contraction",
  review_status: status,
});

describe("boundary review presentation", () => {
  it("orders pending suggestions first and formats boundary changes", () => {
    const accepted = suggestion("accepted", "accepted", 800, 740);
    const pending = suggestion("pending", "pending", 500, 570);
    expect(
      orderedBoundarySuggestions([accepted, pending]).map((item) => item.id),
    ).toEqual(["pending", "accepted"]);
    expect(boundaryDeltaLabel(pending)).toBe("+70 ms");
    expect(boundaryDeltaLabel(accepted)).toBe("-60 ms");
    expect(boundaryReasonLabel(pending)).toBe("延长止音");
    expect(boundaryReasonLabel(accepted)).toBe("提前止音");
  });
});
