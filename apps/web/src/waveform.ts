export interface WaveformPeak {
  min: number;
  max: number;
}

export function waveformPeaks(channels: Float32Array[], buckets: number): WaveformPeak[] {
  if (!channels.length || buckets <= 0) return [];
  const length = Math.max(...channels.map((channel) => channel.length));
  const size = Math.max(1, Math.ceil(length / buckets));
  return Array.from({ length: buckets }, (_, bucket) => {
    let min = 1;
    let max = -1;
    const start = bucket * size;
    const end = Math.min(length, start + size);
    for (const channel of channels) {
      for (let index = start; index < Math.min(end, channel.length); index += 1) {
        min = Math.min(min, channel[index]);
        max = Math.max(max, channel[index]);
      }
    }
    return { min: min === 1 ? 0 : min, max: max === -1 ? 0 : max };
  });
}

export function drawWaveform(canvas: HTMLCanvasElement, buffer: AudioBuffer) {
  const context = canvas.getContext("2d");
  if (!context) return;
  const channels = Array.from({ length: buffer.numberOfChannels }, (_, index) =>
    buffer.getChannelData(index),
  );
  const peaks = waveformPeaks(channels, canvas.width);
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#faf7f0";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.strokeStyle = "#b24c2d";
  context.lineWidth = 1;
  const middle = canvas.height / 2;
  context.beginPath();
  peaks.forEach((peak, x) => {
    context.moveTo(x, middle + peak.min * middle * 0.9);
    context.lineTo(x, middle + peak.max * middle * 0.9);
  });
  context.stroke();
}
