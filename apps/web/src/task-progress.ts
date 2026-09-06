import {
  JOB_STAGE_LABELS,
  type JobResponse,
  type JobStage,
} from "@vocal-score/contracts";

const TASKS = [
  { id: "prepare", label: "音频准备" },
  { id: "separate", label: "人声分离" },
  { id: "transcribe", label: "旋律转谱" },
] as const;

export type TaskId = (typeof TASKS)[number]["id"];
type TaskStatus =
  "waiting" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
export interface TaskStep {
  id: TaskId;
  label: string;
  status: TaskStatus;
  percent: number | null;
  detail: string;
}
type JobProgress = Pick<
  JobResponse,
  "stage" | "status" | "progress" | "error_message"
>;

const STAGE_TASK: Partial<Record<JobStage, TaskId>> = {
  queued: "prepare",
  preprocessing: "prepare",
  separating: "separate",
  transcribing: "transcribe",
  tracking_beats: "transcribe",
  postprocessing: "transcribe",
  rendering: "transcribe",
};

export function initialProgress(): TaskStep[] {
  return TASKS.map((task) => ({
    ...task,
    status: "waiting",
    percent: 0,
    detail: "等待开始",
  }));
}

export function activeProgress(
  task: TaskId,
  detail: string,
  percent: number | null = null,
): TaskStep[] {
  const index = TASKS.findIndex((item) => item.id === task);
  return initialProgress().map((step, position) => {
    if (position < index)
      return { ...step, status: "completed", percent: 100, detail: "已完成" };
    if (position > index) return step;
    return {
      ...step,
      status: "running",
      percent:
        percent === null || !Number.isFinite(percent)
          ? null
          : Math.max(0, Math.min(99, Math.floor(percent))),
      detail,
    };
  });
}

export function completedProgress(): TaskStep[] {
  return initialProgress().map((step) => ({
    ...step,
    status: "completed",
    percent: 100,
    detail: "已完成",
  }));
}

export function stoppedProgress(
  steps: TaskStep[],
  status: "failed" | "cancelled" | "interrupted",
  detail: string,
): TaskStep[] {
  // A transport or render error must not overwrite a failure/cancellation already reported by the worker.
  if (
    steps.some((step) =>
      ["failed", "cancelled", "interrupted"].includes(step.status),
    )
  )
    return steps;
  const active = steps.findIndex((step) => step.status === "running");
  const pending = steps.findIndex((step) => step.status === "waiting");
  const index =
    active >= 0 ? active : pending >= 0 ? pending : steps.length - 1;
  return steps.map((step, position) =>
    position === index ? { ...step, status, detail } : step,
  );
}

export function jobProgress(
  job: JobProgress,
  previous = initialProgress(),
): TaskStep[] {
  if (job.status === "completed") return completedProgress();
  if (job.status === "cancelled" || job.stage === "cancelled") {
    // Cancellation replaces the backend stage. Its stored milestone can be ahead
    // of the last event, especially when a cancelled job is restored after reload.
    const task =
      job.progress >= 0.48
        ? "transcribe"
        : job.progress >= 0.3
          ? "separate"
          : "prepare";
    const observed = previous.findIndex((step) => step.status === "running");
    const milestone = TASKS.findIndex((step) => step.id === task);
    return stoppedProgress(
      observed >= milestone ? previous : activeProgress(task, ""),
      "cancelled",
      "任务已取消",
    );
  }
  const steps = activeProgress(
    STAGE_TASK[job.stage] ?? "prepare",
    JOB_STAGE_LABELS[job.stage],
  );
  if (job.status === "failed")
    return stoppedProgress(
      steps,
      "failed",
      job.error_message || "此步骤处理失败",
    );
  if (job.status === "cancelling")
    return steps.map((step) =>
      step.status === "running" ? { ...step, detail: "正在取消…" } : step,
    );
  return steps;
}

const STATUS_LABELS: Record<TaskStatus, string> = {
  waiting: "待开始",
  running: "处理中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "连接中断",
};

export class TaskProgressPanel {
  private steps = initialProgress();
  private rows;

  constructor(container: HTMLElement) {
    container.classList.add("task-progress");
    this.rows = TASKS.map((task, index) => {
      const row = document.createElement("div");
      row.className = "task-progress-row";
      row.dataset.task = task.id;
      row.innerHTML = `<div class="task-progress-heading"><span><b>${index + 1}</b>${task.label}</span><span class="task-progress-status"></span></div><div class="task-progress-track" role="progressbar" aria-label="${task.label}" aria-valuemin="0" aria-valuemax="100"><i></i></div><p class="task-progress-detail"></p>`;
      container.append(row);
      return {
        row,
        badge: row.querySelector<HTMLElement>(".task-progress-status")!,
        track: row.querySelector<HTMLElement>(".task-progress-track")!,
        fill: row.querySelector<HTMLElement>("i")!,
        detail: row.querySelector<HTMLElement>(".task-progress-detail")!,
      };
    });
    this.render();
  }

  reset() {
    this.steps = initialProgress();
    this.render();
  }
  start(task: TaskId, detail: string, percent: number | null = null) {
    this.steps = activeProgress(task, detail, percent);
    this.render();
  }
  updateJob(job: JobProgress) {
    this.steps = jobProgress(job, this.steps);
    this.render();
  }
  complete() {
    this.steps = completedProgress();
    this.render();
  }
  fail(detail: string) {
    this.steps = stoppedProgress(this.steps, "failed", detail);
    this.render();
  }
  cancel() {
    this.steps = stoppedProgress(this.steps, "cancelled", "任务已取消");
    this.render();
  }
  interrupt() {
    this.steps = stoppedProgress(
      this.steps,
      "interrupted",
      "进度连接中断，刷新页面可恢复",
    );
    this.render();
  }

  private render() {
    this.rows.forEach(({ row, badge, track, fill, detail }, index) => {
      const step = this.steps[index];
      const indeterminate = step.status === "running" && step.percent === null;
      row.dataset.state = step.status;
      row.classList.toggle("indeterminate", indeterminate);
      badge.textContent =
        step.status === "running" && step.percent !== null
          ? `${step.percent}%`
          : STATUS_LABELS[step.status];
      detail.textContent = step.detail;
      track.setAttribute(
        "aria-valuetext",
        `${STATUS_LABELS[step.status]}：${step.detail}`,
      );
      if (step.percent === null) track.removeAttribute("aria-valuenow");
      else track.setAttribute("aria-valuenow", String(step.percent));
      // Unknown progress uses an animated segment, never an invented completion percentage.
      fill.style.width = step.percent === null ? "35%" : `${step.percent}%`;
    });
  }
}
