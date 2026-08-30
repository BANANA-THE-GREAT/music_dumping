import type {
  JobResponse,
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
  ) {
    super(message);
  }
}
export class VocalScoreApi {
  constructor(private baseUrl = "http://localhost:8000") {}
  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, init);
    if (!response.ok) {
      let message = `API request failed (${response.status})`;
      try {
        const body = await response.json();
        message = body.detail ?? message;
      } catch {}
      throw new ApiError(response.status, message);
    }
    return response.status === 204
      ? (undefined as T)
      : (response.json() as Promise<T>);
  }
  upload(file: File): Promise<UploadResponse> {
    const body = new FormData();
    body.append("file", file);
    return this.request("/v1/uploads", { method: "POST", body });
  }
  createJob(uploadId: string, quality: "demo" | "high" = "demo"): Promise<JobResponse> {
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
  cancelJob(id: string): Promise<JobResponse> {
    return this.request(`/v1/jobs/${id}/cancel`, { method: "POST" });
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
}
