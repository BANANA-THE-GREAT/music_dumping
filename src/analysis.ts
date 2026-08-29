import type { MusicalAnalysis, RawNote } from './types';

const MAJOR_PROFILE = [6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88];
const MINOR_PROFILE = [6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17];

export function detectTempo(buffer: AudioBuffer): { bpm: number; confidence: number; envelope: number[] } {
  const channels = Array.from({ length: buffer.numberOfChannels }, (_, i) => buffer.getChannelData(i));
  const hop = Math.max(256, Math.round(buffer.sampleRate / 100));
  const envelope: number[] = [];
  let previous = 0;
  for (let start = 0; start < buffer.length; start += hop) {
    let energy = 0;
    const end = Math.min(buffer.length, start + hop);
    for (let i = start; i < end; i += 4) {
      let sample = 0;
      for (const ch of channels) sample += ch[i] / channels.length;
      energy += sample * sample;
    }
    const flux = Math.max(0, Math.sqrt(energy / Math.max(1, (end - start) / 4)) - previous);
    envelope.push(flux);
    previous = Math.sqrt(energy / Math.max(1, (end - start) / 4));
  }
  const mean = envelope.reduce((a,b) => a+b, 0) / Math.max(1, envelope.length);
  const onset = envelope.map(v => Math.max(0, v - mean * 1.35));
  let bestBpm = 120, best = -Infinity, second = -Infinity;
  for (let bpm = 55; bpm <= 190; bpm++) {
    const lag = Math.round(6000 / bpm);
    let score = 0;
    for (let i = lag; i < onset.length; i++) score += onset[i] * onset[i-lag];
    if (score > best) { second = best; best = score; bestBpm = bpm; }
    else if (score > second) second = score;
  }
  while (bestBpm < 75) bestBpm *= 2;
  while (bestBpm > 170) bestBpm /= 2;
  return { bpm: Math.round(bestBpm), confidence: best > 0 ? Math.min(0.99, Math.max(0.2, (best-second)/best*4)) : 0.2, envelope: onset };
}

export function detectKey(notes: RawNote[]): Pick<MusicalAnalysis,'keyPitchClass'|'mode'> & { confidence: number } {
  const histogram = Array(12).fill(0);
  notes.forEach(n => histogram[((n.pitchMidi%12)+12)%12] += n.durationSeconds * Math.max(.1,n.amplitude));
  const scores: Array<{pc:number;mode:'major'|'minor';score:number}> = [];
  for (let root=0;root<12;root++) for (const mode of ['major','minor'] as const) {
    const profile = mode === 'major' ? MAJOR_PROFILE : MINOR_PROFILE;
    let score=0;
    for(let pc=0;pc<12;pc++) score += histogram[pc] * profile[(pc-root+12)%12];
    scores.push({pc:root,mode,score});
  }
  scores.sort((a,b)=>b.score-a.score);
  const confidence = scores[0].score ? Math.min(.98, Math.max(.25,(scores[0].score-scores[1].score)/scores[0].score*5)) : .25;
  return { keyPitchClass:scores[0].pc, mode:scores[0].mode, confidence };
}

export function detectMeter(notes: RawNote[], bpm: number): { meter: 3|4; confidence: number } {
  const beatSeconds = 60/bpm;
  const scoreFor = (meter:3|4) => {
    const bins = Array(meter).fill(0);
    notes.forEach(n => bins[Math.round(n.startTimeSeconds/beatSeconds)%meter] += n.amplitude);
    const downbeat = bins[0];
    const others = bins.slice(1).reduce((a,b)=>a+b,0)/(meter-1);
    return downbeat/(others+.001);
  };
  const three=scoreFor(3), four=scoreFor(4), meter:3|4 = three>four*1.08?3:4;
  return {meter,confidence:Math.min(.9,Math.max(.25,Math.abs(three-four)/Math.max(three,four)*3))};
}

export function analyzeMusic(buffer: AudioBuffer, notes: RawNote[]): MusicalAnalysis {
  const tempo=detectTempo(buffer), key=detectKey(notes), meter=detectMeter(notes,tempo.bpm);
  return {bpm:tempo.bpm,meter:meter.meter,keyPitchClass:key.keyPitchClass,mode:key.mode,confidence:{bpm:tempo.confidence,meter:meter.confidence,key:key.confidence}};
}
