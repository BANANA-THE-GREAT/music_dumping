export interface AlignmentResult {
  offsetSeconds: number;
  confidence: number;
  matchedCount: number;
}

function nearestDistance(value: number, sortedValues: number[]): number {
  if (!sortedValues.length) return Number.POSITIVE_INFINITY;
  let best = Number.POSITIVE_INFINITY;
  for (const candidate of sortedValues) {
    const distance = Math.abs(candidate - value);
    if (distance < best) best = distance;
    if (candidate > value && candidate - value > best) break;
  }
  return best;
}

export function detectEnergyOnsets(
  samples: Float32Array,
  sampleRate: number,
  frameMs = 20,
): number[] {
  if (!samples.length || sampleRate <= 0 || frameMs <= 0) return [];
  const frameSize = Math.max(1, Math.round((sampleRate * frameMs) / 1000));
  const energies: number[] = [];
  for (let start = 0; start < samples.length; start += frameSize) {
    let energy = 0;
    const end = Math.min(samples.length, start + frameSize);
    for (let index = start; index < end; index += 1) energy += samples[index] ** 2;
    energies.push(Math.sqrt(energy / Math.max(1, end - start)));
  }
  const peak = Math.max(...energies, 0);
  const threshold = Math.max(0.015, peak * 0.12);
  const onsets: number[] = [];
  for (let index = 1; index < energies.length; index += 1) {
    if (energies[index] < threshold || energies[index] <= energies[index - 1] * 1.15) continue;
    const time = (index * frameMs) / 1000;
    if (!onsets.length || time - onsets[onsets.length - 1] >= 0.08) onsets.push(time);
  }
  return onsets;
}

export function estimateGlobalOffset(
  noteStarts: number[],
  audioOnsets: number[],
  rangeSeconds = 2,
  stepSeconds = 0.02,
): AlignmentResult {
  const notes = [...noteStarts].filter(Number.isFinite).sort((a, b) => a - b).slice(0, 32);
  const onsets = [...audioOnsets].filter(Number.isFinite).sort((a, b) => a - b);
  if (!notes.length || !onsets.length) return { offsetSeconds: 0, confidence: 0, matchedCount: 0 };
  let best = { score: Number.POSITIVE_INFINITY, offsetSeconds: 0, matchedCount: 0 };
  for (let offset = -rangeSeconds; offset <= rangeSeconds + 1e-8; offset += stepSeconds) {
    let score = 0;
    let matchedCount = 0;
    for (const note of notes) {
      const distance = nearestDistance(note + offset, onsets);
      score += Math.min(distance, 0.35);
      if (distance <= 0.12) matchedCount += 1;
    }
    score /= notes.length;
    if (score < best.score) best = { score, offsetSeconds: offset, matchedCount };
  }
  return {
    offsetSeconds: Number(best.offsetSeconds.toFixed(3)),
    confidence: Number(Math.max(0, Math.min(1, best.matchedCount / notes.length)).toFixed(3)),
    matchedCount: best.matchedCount,
  };
}
