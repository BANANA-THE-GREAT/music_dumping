import { describe, expect, it } from "vitest";
import {
  activeProgress,
  initialProgress,
  jobProgress,
  stoppedProgress,
} from "./task-progress";

describe("transcription task progress", () => {
  it("restores the active task from a server milestone without inventing a percentage", () => {
    const steps = jobProgress({
      stage: "separating",
      status: "running",
      progress: 0.3,
      error_message: null,
    });
    expect(steps.map((step) => step.status)).toEqual([
      "completed",
      "running",
      "waiting",
    ]);
    expect(steps[1].percent).toBeNull();
  });

  it("keeps transcription active for both demo and real pipeline stage ordering", () => {
    for (const stage of [
      "tracking_beats",
      "transcribing",
      "postprocessing",
      "rendering",
    ] as const) {
      const steps = jobProgress({
        stage,
        status: "running",
        progress: 0.65,
        error_message: null,
      });
      expect(steps.map((step) => step.status)).toEqual([
        "completed",
        "completed",
        "running",
      ]);
      expect(steps[2].percent).toBeNull();
    }
  });

  it("preserves completed work and marks only the failing task", () => {
    const steps = jobProgress({
      stage: "separating",
      status: "failed",
      progress: 0.3,
      error_message: "模型下载失败",
    });
    expect(steps.map((step) => step.status)).toEqual([
      "completed",
      "failed",
      "waiting",
    ]);
    expect(steps[1].detail).toBe("模型下载失败");
    expect(stoppedProgress(steps, "failed", "连接关闭")).toEqual(steps);
  });

  it("uses the last observed task when cancellation replaces the backend stage", () => {
    const before = activeProgress("separate", "分离人声");
    const steps = jobProgress(
      {
        stage: "cancelled",
        status: "cancelled",
        progress: 0.3,
        error_message: null,
      },
      before,
    );
    expect(steps.map((step) => step.status)).toEqual([
      "completed",
      "cancelled",
      "waiting",
    ]);
    expect(stoppedProgress(steps, "failed", "请求结束")).toEqual(steps);
  });

  it("can restore a cancelled task without a prior event", () => {
    const steps = jobProgress({
      stage: "cancelled",
      status: "cancelled",
      progress: 0.65,
      error_message: null,
    });
    expect(steps.map((step) => step.status)).toEqual([
      "completed",
      "completed",
      "cancelled",
    ]);
  });

  it("uses the cancellation milestone when it is ahead of the recovery placeholder", () => {
    const steps = jobProgress(
      {
        stage: "cancelled",
        status: "cancelled",
        progress: 0.65,
        error_message: null,
      },
      activeProgress("prepare", "正在恢复任务进度"),
    );
    expect(steps.map((step) => step.status)).toEqual([
      "completed",
      "completed",
      "cancelled",
    ]);
  });

  it("shows a connection interruption without claiming that server processing failed", () => {
    const steps = stoppedProgress(
      activeProgress("transcribe", "识别旋律", 42),
      "interrupted",
      "刷新恢复",
    );
    expect(steps.map((step) => step.status)).toEqual([
      "completed",
      "completed",
      "interrupted",
    ]);
    expect(steps[2].percent).toBe(42);
  });

  it("uses actual local inference progress but waits for completion before displaying 100%", () => {
    expect(activeProgress("transcribe", "识别旋律", 42.8)[2].percent).toBe(42);
    expect(activeProgress("transcribe", "识别旋律", 100)[2].percent).toBe(99);
    expect(activeProgress("transcribe", "识别旋律", NaN)[2].percent).toBeNull();
    const done = jobProgress({
      stage: "completed",
      status: "completed",
      progress: 1,
      error_message: null,
    });
    expect(
      done.every((step) => step.status === "completed" && step.percent === 100),
    ).toBe(true);
    expect(
      initialProgress().every(
        (step) => step.status === "waiting" && step.percent === 0,
      ),
    ).toBe(true);
  });
});
