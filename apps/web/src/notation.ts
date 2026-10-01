import type { ScoreNote } from "./types";

export interface ScoreSegment {
  index: number | null;
  start: number;
  duration: number;
  continues: boolean;
}

export interface RestSegment {
  start: number;
  duration: number;
}

export function scoreRests(notes: ScoreNote[]): RestSegment[] {
  const rests: RestSegment[] = [];
  let cursor = 0;
  for (const note of [...notes].sort((a, b) => a.startBeat - b.startBeat)) {
    if (note.startBeat > cursor)
      rests.push({ start: cursor, duration: note.startBeat - cursor });
    cursor = Math.max(cursor, note.startBeat + note.durationBeats);
  }
  return rests;
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
          .flatMap((segment) =>
            rhythmParts(segment.duration).map((part, index, parts) => ({
              ...segment,
              ...part,
              continues: segment.continues || index < parts.length - 1,
            })),
          )
          .map((segment) => {
            const n = segment.index === null ? null : notes[segment.index];
            const label = n
              ? `${n.accidental === 1 ? "&#9839;" : n.accidental === -1 ? "&#9837;" : ""}${n.degree}`
              : "0";
            const restTiming = n
              ? ""
              : `data-rest-start="${segment.start}" data-rest-end="${segment.start + segment.duration}"`;
            return `<span class="jp-note${n ? "" : " rest"}" ${n ? `data-note="${segment.index}" tabindex="0" role="button" aria-label="Note ${segment.index! + 1}"` : restTiming}><b>${label}${"&middot;".repeat(segment.dots)}</b><em>${n && n.octave > 0 ? "&middot;".repeat(n.octave) : ""}</em><i>${n && n.octave < 0 ? "&middot;".repeat(-n.octave) : ""}</i><small>${"&#9473;".repeat(segment.underlines)}</small>${n && segment.continues ? '<sup class="jp-tie">&#8994;</sup>' : ""}</span>${'<span class="jp-extension">&#8212;</span>'.repeat(segment.extensions)}`;
          })
          .join("")}</div>`,
    )
    .join("");
}

export function rhythmParts(duration: number) {
  const parts: Array<{
    duration: number;
    dots: number;
    underlines: number;
    extensions: number;
  }> = [];
  let remaining = duration;
  while (remaining > 1e-8) {
    if (remaining >= 2) {
      const whole = Math.floor(remaining);
      parts.push({
        duration: whole,
        dots: 0,
        underlines: 0,
        extensions: whole - 1,
      });
      remaining -= whole;
      continue;
    }
    let base = 1;
    while (base > remaining + 1e-8) base /= 2;
    const dots =
      remaining >= base * 1.75 - 1e-8
        ? 2
        : remaining >= base * 1.5 - 1e-8
          ? 1
          : 0;
    const length = base * (dots === 2 ? 1.75 : dots === 1 ? 1.5 : 1);
    parts.push({
      duration: length,
      dots,
      underlines: Math.round(Math.log2(1 / base)),
      extensions: 0,
    });
    remaining -= length;
  }
  return parts;
}
