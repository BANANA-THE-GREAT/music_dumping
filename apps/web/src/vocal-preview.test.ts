import { it, expect } from "vitest";
import { audioBlob } from "./vocal-preview";
it("encodes local separated audio as playable PCM WAV", async () => {
  const buffer = {
    numberOfChannels: 1,
    length: 3,
    sampleRate: 22050,
    getChannelData: () => new Float32Array([-1, 0, 1]),
  } as unknown as AudioBuffer;
  const bytes = await audioBlob(buffer).arrayBuffer();
  const data = new DataView(bytes);
  expect(new TextDecoder().decode(bytes.slice(0, 4))).toBe("RIFF");
  expect(data.getUint32(24, true)).toBe(22050);
  expect(data.getUint32(40, true)).toBe(6);
  expect(data.getInt16(44, true)).toBe(-32768);
  expect(data.getInt16(48, true)).toBe(32767);
});
