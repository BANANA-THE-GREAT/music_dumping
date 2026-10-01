import type {
  BoundarySuggestion,
  ScoreProjectNote,
} from "@vocal-score/contracts";

const STATUS_ORDER = { pending: 0, accepted: 1, rejected: 2, superseded: 3 } as const;

export function orderedBoundarySuggestions(
  suggestions: BoundarySuggestion[],
): BoundarySuggestion[] {
  return [...suggestions].sort(
    (left, right) =>
      STATUS_ORDER[left.review_status] - STATUS_ORDER[right.review_status] ||
      left.original_end_ms - right.original_end_ms,
  );
}

export function reviewableBoundarySuggestions(
  suggestions: BoundarySuggestion[],
  notes: ScoreProjectNote[],
): BoundarySuggestion[] {
  const sourceIds = new Set(
    notes.flatMap((note) => note.source_note_ids ?? []),
  );
  return suggestions.filter(
    (suggestion) =>
      suggestion.review_status === "superseded" ||
      sourceIds.has(suggestion.source_note_id),
  );
}

export function boundaryDeltaLabel(suggestion: BoundarySuggestion): string {
  const delta = suggestion.proposed_end_ms - suggestion.original_end_ms;
  return `${delta > 0 ? "+" : ""}${delta} ms`;
}

export function boundaryReasonLabel(suggestion: BoundarySuggestion): string {
  return suggestion.reason === "f0_voicing_extension" ? "延长止音" : "提前止音";
}

export function boundarySupersededLabel(suggestion: BoundarySuggestion): string {
  switch (suggestion.superseded_reason) {
    case "target_deleted":
      return "目标音符已删除";
    case "target_structure_changed":
      return "音符结构已人工修改";
    default:
      return "音符时值已人工修改";
  }
}
