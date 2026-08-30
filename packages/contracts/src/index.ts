export type JobStatus =
  "queued" | "running" | "completed" | "failed" | "cancelling" | "cancelled";
export type JobStage =
  | "queued"
  | "preprocessing"
  | "separating"
  | "tracking_beats"
  | "transcribing"
  | "postprocessing"
  | "rendering"
  | "completed"
  | "cancelled";
export interface UploadResponse {
  id: string;
  file_name: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  created_at: string;
}
export interface JobResponse {
  id: string;
  upload_id: string;
  status: JobStatus;
  stage: JobStage;
  progress: number;
  project_id: string | null;
  error_code: string | null;
  error_message: string | null;
  retryable: boolean;
  created_at: string;
  updated_at: string;
}
export interface ScoreProjectNote {
  id: string;
  source_start_ms: number;
  source_end_ms: number;
  pitch_midi: number;
  confidence: number;
  quantized_start: number;
  quantized_duration: number;
  origin: "model" | "user";
}
export interface ScoreProject {
  schema_version: "1.0";
  project_id: string;
  source: {
    file_name: string;
    duration_ms: number;
    audio_object_key: string;
    vocal_object_key: string | null;
  };
  analysis: {
    tempo_map: Array<{ time_ms: number; bpm: number }>;
    meter_map: Array<{ beat: number; numerator: number; denominator: number }>;
    key_map: Array<{ beat: number; tonic: number; mode: "major" | "minor" }>;
    confidence: Record<string, number>;
  };
  notes: ScoreProjectNote[];
  pipeline: Array<{
    stage: string;
    version: string;
    parameters: Record<string, unknown>;
  }>;
  revision: number;
}
export interface RequantizeRequest {
  expected_revision: number;
  bpm: number;
  numerator: number;
  denominator: 2 | 4 | 8 | 16;
  tonic: number;
  mode: "major" | "minor";
  grid: number;
}
export const JOB_STAGE_LABELS: Record<JobStage, string> = {
  queued: "等待处理",
  preprocessing: "标准化音频",
  separating: "分离人声",
  tracking_beats: "识别节拍",
  transcribing: "识别旋律",
  postprocessing: "清理与量化",
  rendering: "生成乐谱",
  completed: "处理完成",
  cancelled: "已取消",
};
