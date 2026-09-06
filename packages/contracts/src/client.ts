import type {
  JobResponse,
  MelodyOptions,
  ProjectSummary,
  RequantizeRequest,
  ScoreProject,
  ScoreProjectNote,
  UploadResponse,
} from "./index";
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
  }
}
export class VocalScoreApi {
  constructor(private baseUrl = "/api") {}
  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, init);
    if (!response.ok) {
      let message = `API request failed (${response.status})`;
      let detail: unknown;
      try {
        const body = await response.json();
        detail = body.detail;
        if (typeof detail === "string") message = detail;
        else if (detail && typeof detail === "object" && "code" in detail)
          message = String(detail.code);
      } catch {}
      throw new ApiError(response.status, message, detail);
    }
    return response.status === 204
      ? (undefined as T)
      : (response.json() as Promise<T>);
  }
  upload(file: File, signal?: AbortSignal): Promise<UploadResponse> {
    const body = new FormData();
    body.append("file", file);
    return this.request("/v1/uploads", { method: "POST", body, signal });
  }
  createJob(
    uploadId: string,
    quality: "demo" | "high" = "demo",
  ): Promise<JobResponse> {
    return this.request("/v1/jobs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        upload_id: uploadId,
        options:
          quality === "high"
            ? { separator: "demucs", transcriber: "basic_pitch" }
            : { separator: "fake", transcriber: "fake" },
      }),
    });
  }
  getJob(id: string): Promise<JobResponse> {
    return this.request(`/v1/jobs/${id}`);
  }
  getProject(id: string): Promise<ScoreProject> {
    return this.request(`/v1/projects/${id}`);
  }
  listProjects(): Promise<ProjectSummary[]> {
    return this.request("/v1/projects");
  }
  deleteProject(id: string): Promise<void> {
    return this.request(`/v1/projects/${id}`, { method: "DELETE" });
  }
  updateProject(
    id: string,
    expectedRevision: number,
    notes: ScoreProjectNote[],
  ): Promise<ScoreProject> {
    return this.request(`/v1/projects/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ expected_revision: expectedRevision, notes }),
    });
  }
  requantizeProject(
    id: string,
    request: RequantizeRequest,
  ): Promise<ScoreProject> {
    return this.request(`/v1/projects/${id}/requantize`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request),
    });
  }
  exportUrl(id: string, format: "midi" | "musicxml"): string {
    return `${this.baseUrl}/v1/projects/${id}/exports/${format}`;
  }
  audioUrl(id: string, variant: "source" | "vocals" = "source"): string {
    return `${this.baseUrl}/v1/projects/${id}/audio${variant === "vocals" ? "?variant=vocals" : ""}`;
  }
  refineMelody(
    id: string,
    expectedRevision: number,
    options: MelodyOptions,
  ): Promise<ScoreProject> {
    return this.request(`/v1/projects/${id}/melody`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ expected_revision: expectedRevision, ...options }),
    });
  }
  cancelJob(id: string): Promise<JobResponse> {
    return this.request(`/v1/jobs/${id}/cancel`, { method: "POST" });
  }
  retryJob(id: string): Promise<JobResponse> {
    return this.request(`/v1/jobs/${id}/retry`, { method: "POST" });
  }
  async waitForJob(
    id: string,
    onProgress: (job: JobResponse) => void,
    signal?: AbortSignal,
  ): Promise<JobResponse> {
    while (true) {
      if (signal?.aborted) throw new DOMException("Cancelled", "AbortError");
      const job = await this.getJob(id);
      onProgress(job);
      if (job.status === "completed") return job;
      if (job.status === "failed" || job.status === "cancelled")
        throw new Error(job.error_message ?? `Job ${job.status}`);
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }

  waitForJobEvents(
    id: string,
    onProgress: (job: JobResponse) => void,
    signal?: AbortSignal,
  ): Promise<JobResponse> {
    if (typeof EventSource === "undefined")
      return this.waitForJob(id, onProgress, signal);
    return new Promise((resolve, reject) => {
      const events = new EventSource(`${this.baseUrl}/v1/jobs/${id}/events`);
      let receivedEvent = false;
      const close = () => events.close();
      signal?.addEventListener(
        "abort",
        () => {
          close();
          reject(new DOMException("Cancelled", "AbortError"));
        },
        { once: true },
      );
      events.addEventListener("progress", (event) => {
        receivedEvent = true;
        const job = JSON.parse(
          (event as MessageEvent<string>).data,
        ) as JobResponse;
        onProgress(job);
        if (job.status === "completed") {
          close();
          resolve(job);
        } else if (job.status === "failed" || job.status === "cancelled") {
          close();
          reject(new Error(job.error_message ?? `Job ${job.status}`));
        }
      });
      events.onerror = () => {
        close();
        if (receivedEvent)
          reject(new Error("Job progress stream ended unexpectedly"));
        else this.waitForJob(id, onProgress, signal).then(resolve, reject);
      };
    });
  }
}
