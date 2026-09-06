import { drawWaveform } from "./waveform";

export function audioBlob(buffer: AudioBuffer): Blob {
  const channels = buffer.numberOfChannels;
  const bytes = new ArrayBuffer(44 + buffer.length * channels * 2);
  const view = new DataView(bytes);
  const text = (offset: number, value: string) =>
    [...value].forEach((v, i) => view.setUint8(offset + i, v.charCodeAt(0)));
  text(0, "RIFF");
  view.setUint32(4, bytes.byteLength - 8, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channels, true);
  view.setUint32(24, buffer.sampleRate, true);
  view.setUint32(28, buffer.sampleRate * channels * 2, true);
  view.setUint16(32, channels * 2, true);
  view.setUint16(34, 16, true);
  text(36, "data");
  view.setUint32(40, bytes.byteLength - 44, true);
  const data = Array.from({ length: channels }, (_, i) =>
    buffer.getChannelData(i),
  );
  for (let i = 0; i < buffer.length; i++)
    for (let c = 0; c < channels; c++) {
      const value = Math.max(-1, Math.min(1, data[c][i]));
      view.setInt16(
        44 + (i * channels + c) * 2,
        value * (value < 0 ? 32768 : 32767),
        true,
      );
    }
  return new Blob([bytes], { type: "audio/wav" });
}

export class VocalPreview {
  private source = "";
  private vocals = "";
  private version = 0;
  private buffer: AudioBuffer | null = null;
  private radio: HTMLInputElement;
  private status: HTMLElement;
  private canvas: HTMLCanvasElement;
  constructor(
    private audio: HTMLAudioElement,
    private container: HTMLElement,
  ) {
    container.innerHTML = `<div class="audio-modes" role="group" aria-label="试听音源"><label><input type="radio" name="audio-mode" value="source" checked>原曲</label><label><input type="radio" name="audio-mode" value="vocals" disabled>分离人声</label></div><output id="vocal-status">尚无人声分离结果</output><canvas id="vocal-waveform" width="900" height="100" aria-label="分离人声波形"></canvas>`;
    this.radio = container.querySelector<HTMLInputElement>('[value="vocals"]')!;
    this.status = container.querySelector("output")!;
    this.canvas = container.querySelector("canvas")!;
    container
      .querySelectorAll<HTMLInputElement>("input")
      .forEach((input) =>
        input.addEventListener(
          "change",
          () => void this.switch(input.value === "vocals"),
        ),
      );
  }
  setSource(url: string) {
    ++this.version;
    if (this.source.startsWith("blob:")) URL.revokeObjectURL(this.source);
    if (this.vocals.startsWith("blob:")) URL.revokeObjectURL(this.vocals);
    this.source = url;
    this.vocals = "";
    this.buffer = null;
    this.radio.disabled = true;
    this.container.querySelector<HTMLInputElement>(
      '[value="source"]',
    )!.checked = true;
    this.audio.pause();
    if (url) this.audio.src = url;
    else {
      this.audio.removeAttribute("src");
      this.audio.load();
    }
    this.canvas
      .getContext("2d")!
      .clearRect(0, 0, this.canvas.width, this.canvas.height);
    this.status.textContent = "尚无人声分离结果";
  }
  setVocals(url: string, buffer: AudioBuffer | null = null) {
    if (this.vocals.startsWith("blob:")) URL.revokeObjectURL(this.vocals);
    this.vocals = url;
    this.buffer = buffer;
    this.radio.disabled = !url;
    this.status.textContent = url ? "人声分离结果可试听" : "此项目没有分离人声";
    if (buffer) drawWaveform(this.canvas, buffer);
  }
  private async switch(vocals: boolean) {
    const version = ++this.version;
    const time = this.audio.currentTime,
      playing = !this.audio.paused;
    this.audio.pause();
    try {
      if (vocals && !this.buffer) {
        this.status.textContent = "正在载入分离人声…";
        const response = await fetch(this.vocals);
        if (!response.ok)
          throw new Error("分离人声不可用，请重新运行高质量转录");
        const context = new AudioContext();
        let buffer: AudioBuffer;
        try {
          buffer = await context.decodeAudioData(await response.arrayBuffer());
        } finally {
          await context.close();
        }
        if (version !== this.version) return;
        this.buffer = buffer;
        drawWaveform(this.canvas, buffer);
      }
      if (version !== this.version) return;
      this.audio.src = vocals ? this.vocals : this.source;
      this.audio.addEventListener(
        "loadedmetadata",
        () => {
          if (version !== this.version) return;
          this.audio.currentTime = Math.min(time, this.audio.duration || 0);
          if (playing) void this.audio.play().catch(() => {});
        },
        { once: true },
      );
      this.status.textContent = vocals ? "分离人声" : "原曲";
    } catch (error) {
      if (version !== this.version) return;
      this.status.textContent =
        error instanceof Error ? error.message : "人声载入失败";
      this.container.querySelector<HTMLInputElement>(
        '[value="source"]',
      )!.checked = true;
      this.audio.src = this.source;
    }
  }
}
