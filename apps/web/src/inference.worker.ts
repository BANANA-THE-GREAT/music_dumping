import {
  BasicPitch,
  addPitchBendsToNoteEvents,
  noteFramesToTime,
  outputToNotesPoly,
} from "@spotify/basic-pitch";

self.onmessage = async (
  event: MessageEvent<{
    samples: Float32Array;
    threshold: number;
    modelUrl: string;
  }>,
) => {
  try {
    const frames: number[][] = [],
      onsets: number[][] = [],
      contours: number[][] = [];
    const model = new BasicPitch(event.data.modelUrl);
    await model.evaluateModel(
      event.data.samples,
      (f, o, c) => {
        frames.push(...f);
        onsets.push(...o);
        contours.push(...c);
      },
      (progress) => self.postMessage({ progress }),
    );
    const notes = noteFramesToTime(
      addPitchBendsToNoteEvents(
        contours,
        outputToNotesPoly(frames, onsets, event.data.threshold, 0.28, 5),
      ),
    );
    self.postMessage({ notes });
  } catch (error) {
    self.postMessage({
      error: error instanceof Error ? error.message : String(error),
    });
  }
};
