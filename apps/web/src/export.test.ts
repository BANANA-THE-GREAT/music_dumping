import { describe, expect, it } from "vitest";
import { Midi } from "@tonejs/midi";
import { buildMidiBytes, buildMusicXml } from "./export";
import { cleanAndQuantize, demoNotes } from "./music";
import type { MusicalAnalysis } from "./types";
const analysis: MusicalAnalysis = {
  bpm: 96,
  meter: 3,
  meterDenominator: 4,
  keyPitchClass: 7,
  mode: "minor",
  confidence: { bpm: 1, meter: 1, key: 1 },
};
const notes = cleanAndQuantize(demoNotes(), 96, 67, "minor");
describe("standard exports", () => {
  it("writes parseable MIDI with tempo, meter and notes", () => {
    const bytes = buildMidiBytes(notes, analysis);
    const midi = new Midi(bytes.buffer as ArrayBuffer);
    expect(midi.header.tempos[0].bpm).toBeCloseTo(96);
    expect(midi.header.timeSignatures[0].timeSignature).toEqual([3, 4]);
    expect(midi.tracks[0].notes.length).toBe(notes.length);
  });
  it("writes MusicXML metadata and every note", () => {
    const xml = buildMusicXml(notes, analysis);
    expect(xml).toContain("<beats>3</beats>");
    expect(xml).toContain("<mode>minor</mode>");
    expect((xml.match(/<note>/g) || []).length).toBe(notes.length);
    expect(xml.endsWith("</score-partwise>")).toBe(true);
  });
  it("preserves compound meter denominator", () => {
    const compound = {
      ...analysis,
      meter: 6 as const,
      meterDenominator: 8 as const,
    };
    const midi = new Midi(
      buildMidiBytes(notes, compound).buffer as ArrayBuffer,
    );
    expect(midi.header.timeSignatures[0].timeSignature).toEqual([6, 8]);
    expect(buildMusicXml(notes, compound)).toContain(
      "<beat-type>8</beat-type>",
    );
  });
});
