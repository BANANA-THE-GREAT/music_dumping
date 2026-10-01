import { describe, expect, it, vi } from "vitest";
import {
  activeNoteIndices,
  playbackTimeline,
  scheduleVoice,
  ScorePlayer,
} from "./playback";
import { cleanAndQuantize, demoNotes } from "./music";

describe("audio-clock playback", () => {
  it("keeps rests, overlaps and exact end boundaries", () => {
    const n = cleanAndQuantize(demoNotes(), 120)[0];
    const timeline = playbackTimeline(
      [
        { ...n, startBeat: 1, durationBeats: 2 },
        { ...n, startBeat: 2, durationBeats: 2 },
      ],
      120,
    );
    expect(activeNoteIndices(timeline, 0)).toEqual([]);
    expect(activeNoteIndices(timeline, 1)).toEqual([0, 1]);
    expect(activeNoteIndices(timeline, 1.5)).toEqual([1]);
    expect(activeNoteIndices(timeline, 2)).toEqual([]);
    expect(() => playbackTimeline([], 0)).toThrow();
  });
  it("schedules absolute starts and a sustained envelope rather than timer callbacks", () => {
    const parameter = {
      setValueAtTime: vi.fn(),
      linearRampToValueAtTime: vi.fn(),
    };
    const gain = {
      gain: parameter,
      connect: vi.fn().mockReturnThis(),
      disconnect: vi.fn(),
    };
    const oscillator = {
      frequency: { setValueAtTime: vi.fn() },
      connect: vi.fn().mockReturnValue(gain),
      start: vi.fn(),
      stop: vi.fn(),
      disconnect: vi.fn(),
    };
    const context = {
      createOscillator: () => oscillator,
      createGain: () => gain,
    };
    scheduleVoice(
      context as unknown as BaseAudioContext,
      {} as AudioNode,
      { index: 0, pitch: 69, start: 0.5, end: 1.5 },
      10,
    );
    expect(oscillator.start).toHaveBeenCalledWith(10.5);
    expect(oscillator.stop).toHaveBeenCalledWith(11.53);
    expect(parameter.setValueAtTime).toHaveBeenCalledWith(0.11, 11.5);
    expect(parameter.linearRampToValueAtTime).toHaveBeenCalledWith(0, 11.525);
  });
  it("cannot start a cancelled play while resume is pending", async () => {
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    let resume!: () => void;
    const context = {
      resume: () =>
        new Promise<void>((resolve) => {
          resume = resolve;
        }),
      createGain: vi.fn(),
    };
    const player = new ScorePlayer(() => context as unknown as AudioContext);
    const pending = player.play(
      cleanAndQuantize(demoNotes(), 120),
      120,
      vi.fn(),
      vi.fn(),
    );
    player.stop();
    resume();
    await pending;
    expect(context.createGain).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
