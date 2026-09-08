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
  project_name?: string | null;
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
  source_note_ids?: string[];
  pitch_midi: number;
  confidence: number;
  quantized_start: number;
  quantized_duration: number;
  origin: "model" | "user";
}
export interface PitchBendPoint {
  offset_ms: number;
  cents: number;
}
export interface PerformanceNote {
  id: string;
  source_start_ms: number;
  source_end_ms: number;
  source_note_ids?: string[];
  pitch_midi: number;
  confidence: number;
  origin: "model" | "user";
  pitch_bends: PitchBendPoint[];
}
export interface QuantizationSettings {
  enabled: boolean;
  grid: number;
  strength: number;
  offset_ms: number;
  conflicts: Array<{ beat: number; note_ids: string[] }>;
}
export interface AudioAlignment {
  offset_ms: number;
  source: "manual" | "automatic" | "default";
  status: "unconfirmed" | "confirmed";
  candidate_offset_ms?: number | null;
  confidence?: number | null;
}
export interface ModelProvenance {
  name: string;
  implementation: string;
  code_revision: string;
  model_revision?: string | null;
  weight_sha256?: string | null;
  parameters: Record<string, unknown>;
  device?: string | null;
}
export interface F0TrackArtifact {
  object_key: string;
  format: "jsonl";
  frame_period_ms: number;
  frame_count: number;
  voiced_frame_count: number;
  duration_ms: number;
  provenance: ModelProvenance;
}
export interface F0Frame {
  time_seconds: number;
  f0_hz: number;
  periodicity: number;
}
export interface BoundarySuggestion {
  id: string;
  source_note_id: string;
  kind: "adjust_end";
  original_end_ms: number;
  proposed_end_ms: number;
  confidence: number;
  reason: "f0_voicing_extension" | "f0_voicing_contraction";
  review_status: "pending" | "accepted" | "rejected";
  reviewed_revision?: number | null;
  accepted_from_origin?: "model" | "user" | null;
  accepted_from_quantized_duration?: number | null;
  review_batch_id?: string | null;
}
export interface TranscriptionEvidence {
  note_model: ModelProvenance;
  f0_track?: F0TrackArtifact | null;
  boundary_suggestions: BoundarySuggestion[];
  last_boundary_batch_id?: string | null;
}
export interface BoundaryBatchReviewRequest {
  expected_revision: number;
  threshold: number;
  action: "preview" | "accept" | "reset";
}
export interface AudioAlignmentRequest {
  expected_revision: number;
  offset_ms: number;
  source: "manual" | "automatic" | "default";
  status: "unconfirmed" | "confirmed";
}
export interface ScoreProject {
  schema_version: "1.0";
  project_id: string;
  project_group_id?: string | null;
  project_name?: string | null;
  score_name?: string | null;
  engine?: string | null;
  source: {
    file_name: string;
    duration_ms: number;
    audio_object_key: string;
    vocal_object_key: string | null;
  };
  transcription_input?: {
    variant: "source" | "vocal_stem";
    object_key: string;
    separator?: string | null;
  } | null;
  analysis: {
    tempo_map: Array<{ time_ms: number; bpm: number }>;
    meter_map: Array<{ beat: number; numerator: number; denominator: number }>;
    key_map: Array<{ beat: number; tonic: number; mode: "major" | "minor" }>;
    confidence: Record<string, number>;
  };
  notes: ScoreProjectNote[];
  performance_notes?: PerformanceNote[] | null;
  quantization?: QuantizationSettings;
  audio_alignment?: AudioAlignment;
  raw_notes?: ScoreProjectNote[] | null;
  transcription_evidence?: TranscriptionEvidence | null;
  pipeline: Array<{
    stage: string;
    version: string;
    parameters: Record<string, unknown>;
  }>;
  revision: number;
}
export interface ProjectSummary {
  project_id: string;
  file_name: string;
  duration_ms: number;
  note_count: number;
  revision: number;
  updated_at: string;
}
export interface ProjectCatalogSummary extends ProjectSummary {
  project_group_id: string;
  upload_id: string;
  project_name: string;
  score_name: string;
  engine: string;
}
export interface RequantizeRequest {
  expected_revision: number;
  bpm: number;
  numerator: number;
  denominator: 2 | 4 | 8 | 16;
  tonic: number;
  mode: "major" | "minor";
  enabled?: boolean;
  grid: number;
  strength?: number;
  offset_ms?: number;
  tempo_map?: Array<{ time_ms: number; bpm: number }>;
}
export interface BoundarySuggestionReviewRequest {
  expected_revision: number;
  action: "accept" | "reject" | "reset";
}
export interface MelodyOptions {
  mode: "raw" | "conservative" | "balanced";
  low_pitch: number;
  high_pitch: number;
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
