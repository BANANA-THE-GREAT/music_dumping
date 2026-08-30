export interface RawNote {
  pitchMidi: number;
  amplitude: number;
  startTimeSeconds: number;
  durationSeconds: number;
}

export interface ScoreNote extends RawNote {
  id: number;
  startBeat: number;
  durationBeats: number;
  degree: number;
  accidental: number;
  octave: number;
}

export interface MusicalAnalysis {
  bpm: number;
  meter: 2 | 3 | 4 | 6;
  meterDenominator: 4 | 8;
  keyPitchClass: number;
  mode: "major" | "minor";
  confidence: { bpm: number; meter: number; key: number };
}
