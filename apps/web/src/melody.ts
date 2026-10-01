import type { RawNote } from "./types";
import type { MelodyOptions } from "@vocal-score/contracts";

export function refineLocalMelody(
  raw: RawNote[],
  options: MelodyOptions,
): RawNote[] {
  if (options.mode === "raw") return raw.map((n) => ({ ...n }));
  const notes = raw
    .filter(
      (n) =>
        n.pitchMidi >= options.low_pitch &&
        n.pitchMidi <= options.high_pitch &&
        n.amplitude >= 0.2 &&
        n.durationSeconds >= 0.06,
    )
    .sort((a, b) => a.startTimeSeconds - b.startTimeSeconds);
  if (!notes.length) return [];
  const end = (n: RawNote) => n.startTimeSeconds + n.durationSeconds;
  const boundaries = [
    ...new Set(notes.flatMap((n) => [n.startTimeSeconds, end(n)])),
  ].sort((a, b) => a - b);
  let prior = new Map<number, { score: number; parent: number }>([
    [-1, { score: 0, parent: -1 }],
  ]);
  const layers: (typeof prior)[] = [];
  for (let t = 0; t < boundaries.length - 1; t++) {
    const active = notes
      .map((n, i) => ({ n, i }))
      .filter(
        ({ n }) =>
          n.startTimeSeconds <= boundaries[t] && end(n) > boundaries[t],
      )
      .sort((a, b) => b.n.amplitude - a.n.amplitude)
      .slice(0, 8)
      .map((v) => v.i);
    const layer: typeof prior = new Map();
    for (const i of active.length ? active : [-1]) {
      let best = { score: -Infinity, parent: -1 };
      for (const [j, state] of prior) {
        const leap =
          i >= 0 && j >= 0
            ? Math.abs(notes[i].pitchMidi - notes[j].pitchMidi)
            : 0;
        const penalty =
          (options.mode === "balanced" ? 0.05 : 0.025) * Math.min(leap, 12) +
          (leap ? 0.02 : 0);
        const score =
          state.score +
          (i < 0
            ? 0
            : (boundaries[t + 1] - boundaries[t]) * notes[i].amplitude) -
          penalty;
        if (score > best.score) best = { score, parent: j };
      }
      layer.set(i, best);
    }
    layers.push(layer);
    prior = layer;
  }
  let state = [...prior].sort((a, b) => b[1].score - a[1].score)[0][0];
  const path: number[] = [];
  for (let i = layers.length - 1; i >= 0; i--) {
    path.unshift(state);
    state = layers[i].get(state)!.parent;
  }
  const fragments: Array<RawNote & { index: number }> = [];
  path.forEach((index, t) => {
    if (index < 0) return;
    const previous = fragments.at(-1);
    if (
      previous?.index === index &&
      Math.abs(end(previous) - boundaries[t]) < 1e-8
    )
      previous.durationSeconds = boundaries[t + 1] - previous.startTimeSeconds;
    else
      fragments.push({
        ...notes[index],
        index,
        startTimeSeconds: boundaries[t],
        durationSeconds: boundaries[t + 1] - boundaries[t],
      });
  });
  const result: RawNote[] = [];
  for (const n of fragments.filter((n) => n.durationSeconds >= 0.06)) {
    const previous = result.at(-1);
    const gap = previous ? n.startTimeSeconds - end(previous) : Infinity;
    if (
      previous &&
      previous.pitchMidi === n.pitchMidi &&
      gap >= 0 &&
      gap <= (options.mode === "balanced" ? 0.08 : 0.04) &&
      Math.min(previous.durationSeconds, n.durationSeconds) < 0.18
    ) {
      previous.durationSeconds = end(n) - previous.startTimeSeconds;
      previous.amplitude = Math.min(previous.amplitude, n.amplitude);
    } else result.push({ ...n });
  }
  return result;
}
