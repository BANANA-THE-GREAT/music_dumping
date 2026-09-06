import type { ScoreNote } from "./types";

export interface ScoreSegment {
  index: number | null;
  start: number;
  duration: number;
  continues: boolean;
}

export function scoreMeasures(
  notes: ScoreNote[],
  beats: number,
): ScoreSegment[][] {
  if (!notes.length) return [];
  const end = Math.max(...notes.map((n) => n.startBeat + n.durationBeats));
  const measures: ScoreSegment[][] = Array.from(
    { length: Math.ceil(end / beats) },
    () => [],
  );
  const append = (index: number | null, start: number, finish: number) => {
    while (start < finish - 1e-8) {
      const bar = Math.floor((start + 1e-8) / beats);
      const next = Math.min(finish, (bar + 1) * beats);
      measures[bar].push({
        index,
        start,
        duration: next - start,
        continues: next < finish - 1e-8,
      });
      start = next;
    }
  };
  let cursor = 0;
  notes
    .map((note, index) => ({ note, index }))
    .sort((a, b) => a.note.startBeat - b.note.startBeat)
    .forEach(({ note, index }) => {
      if (note.startBeat > cursor) append(null, cursor, note.startBeat);
      append(index, note.startBeat, note.startBeat + note.durationBeats);
      cursor = Math.max(cursor, note.startBeat + note.durationBeats);
    });
  return measures;
}

export function renderJianpu(notes: ScoreNote[], beats: number): string {
  return scoreMeasures(notes, beats)
    .map(
      (segments, bar) =>
        `<div class="jp-measure" aria-label="Measure ${bar + 1}">${segments
          .map((segment) => {
            const n = segment.index === null ? null : notes[segment.index];
            const label = n
              ? `${n.accidental === 1 ? "&#9839;" : n.accidental === -1 ? "&#9837;" : ""}${n.degree}`
              : "0";
            return `<span class="jp-note" ${n ? `data-note="${segment.index}" tabindex="0" role="button" aria-label="Note ${segment.index! + 1}"` : ""}><b>${label}</b><em>${n && n.octave > 0 ? "&middot;".repeat(n.octave) : ""}</em><i>${n && n.octave < 0 ? "&middot;".repeat(-n.octave) : ""}</i><small>${segment.duration < 1 ? "&#9473;".repeat(Math.round(Math.log2(1 / segment.duration))) : ""}</small>${segment.continues ? '<sup class="jp-tie">&#8994;</sup>' : ""}</span>${segment.duration >= 2 ? '<span class="jp-extension">&#8212;</span>'.repeat(Math.floor(segment.duration) - 1) : ""}`;
          })
          .join("")}</div>`,
    )
    .join("");
}
