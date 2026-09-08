import type { ScoreNote } from "./types";

export interface TimedNote {
  index: number;
  pitch: number;
  start: number;
  end: number;
}
export function playbackTimeline(notes: ScoreNote[], bpm: number): TimedNote[] {
  if (!Number.isFinite(bpm) || bpm <= 0) throw new Error("Invalid tempo");
  return notes.map((n, index) => ({
    index,
    pitch: n.pitchMidi,
    start: (n.startBeat * 60) / bpm,
    end: ((n.startBeat + n.durationBeats) * 60) / bpm,
  }));
}

export function activeNoteIndices(
  timeline: TimedNote[],
  seconds: number,
): number[] {
  return timeline
    .filter((n) => n.start <= seconds && n.end > seconds)
    .map((n) => n.index);
}

export function scheduleVoice(
  context: BaseAudioContext,
  destination: AudioNode,
  note: TimedNote,
  origin: number,
) {
  const oscillator = context.createOscillator();
  const gain = context.createGain();
  const start = origin + note.start;
  const end = origin + note.end;
  const attack = Math.min(0.008, (end - start) / 4);
  oscillator.type = "triangle";
  oscillator.frequency.setValueAtTime(
    440 * 2 ** ((note.pitch - 69) / 12),
    start,
  );
  gain.gain.setValueAtTime(0, start);
  gain.gain.linearRampToValueAtTime(0.14, start + attack);
  gain.gain.linearRampToValueAtTime(
    0.11,
    start + Math.min(0.04, (end - start) / 2),
  );
  gain.gain.setValueAtTime(0.11, end);
  gain.gain.linearRampToValueAtTime(0, end + 0.025);
  oscillator.connect(gain).connect(destination);
  oscillator.onended = () => {
    oscillator.disconnect();
    gain.disconnect();
  };
  oscillator.start(start);
  oscillator.stop(end + 0.03);
  return oscillator;
}

export class ScorePlayer {
  private context: AudioContext | null = null;
  private voices: OscillatorNode[] = [];
  private master: GainNode | null = null;
  private frame = 0;
  private generation = 0;
  private clearHighlight: (() => void) | null = null;

  constructor(
    private createContext = () =>
      new AudioContext({ latencyHint: "interactive" }),
  ) {}

  async play(
    notes: ScoreNote[],
    bpm: number,
    highlight: (indices: number[]) => void,
    ended: () => void,
    volume = 0.8,
  ) {
    this.stop();
    const generation = this.generation;
    const timeline = playbackTimeline(notes, bpm);
    if (!timeline.length) {
      ended();
      return;
    }
    const context = (this.context ??= this.createContext());
    await context.resume();
    if (generation !== this.generation) return;
    const master = (this.master = context.createGain());
    master.gain.value = Math.max(0, Math.min(1, volume));
    const compressor = context.createDynamicsCompressor();
    master.connect(compressor).connect(context.destination);
    this.clearHighlight = () => highlight([]);
    // Schedule on the audio clock, independently of rendering and JS timer jitter.
    const origin = context.currentTime + 0.06;
    this.voices = timeline.map((n) =>
      scheduleVoice(context, master, n, origin),
    );
    const lastVoice = this.voices.reduce(
      (last, voice, i) => (timeline[i].end > timeline[last].end ? i : last),
      0,
    );
    const finishVoice = this.voices[lastVoice];
    const disconnectVoice = finishVoice.onended;
    finishVoice.onended = (event) => {
      disconnectVoice?.call(finishVoice, event);
      if (generation === this.generation) {
        this.voices = [];
        this.master = null;
        this.stop();
        ended();
      }
      master.disconnect();
      compressor.disconnect();
    };
    const tick = () => {
      if (generation !== this.generation) return;
      const outputTime = context.getOutputTimestamp?.().contextTime ?? 0;
      const audibleTime =
        outputTime > 0
          ? outputTime
          : context.currentTime - (context.outputLatency || 0);
      highlight(activeNoteIndices(timeline, audibleTime - origin));
      this.frame = requestAnimationFrame(tick);
    };
    tick();
  }

  stop() {
    ++this.generation;
    cancelAnimationFrame(this.frame);
    if (this.context && this.master) {
      const now = this.context.currentTime;
      const master = this.master;
      master.gain.cancelScheduledValues(now);
      master.gain.setValueAtTime(master.gain.value, now);
      master.gain.linearRampToValueAtTime(0, now + 0.012);
      for (const voice of this.voices) voice.stop(now + 0.015);
    }
    this.voices = [];
    this.master = null;
    this.clearHighlight?.();
    this.clearHighlight = null;
  }
}
