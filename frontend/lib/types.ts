export type PipelineStage =
  | "discovered"
  | "pending_detail"
  | "enriched"
  | "pending_score"
  | "scored"
  | "pending_tailor"
  | "tailored"
  | "pending_apply"
  | "applied";

export const PIPELINE_STAGES: PipelineStage[] = [
  "discovered",
  "pending_detail",
  "enriched",
  "pending_score",
  "scored",
  "pending_tailor",
  "tailored",
  "pending_apply",
  "applied",
];

export interface Job {
  url: string;
  title?: string | null;
  site?: string | null;
  location?: string | null;
  salary?: string | null;
  description?: string | null;
  full_description?: string | null;
  fit_score?: number | null;
  score_reasoning?: string | null;
  application_url?: string | null;
  tailored_resume_path?: string | null;
  cover_letter_path?: string | null;
  apply_status?: string | null;
  apply_error?: string | null;
  discovered_at?: string | null;
  detail_scraped_at?: string | null;
  scored_at?: string | null;
  tailored_at?: string | null;
  cover_letter_at?: string | null;
  applied_at?: string | null;
  last_attempted_at?: string | null;
  tailor_attempts?: number | null;
  cover_attempts?: number | null;
  apply_attempts?: number | null;
  viewed_at?: string | null;
  [key: string]: unknown;
}

export interface StatsResponse {
  total: number;
  pending_detail: number;
  with_description: number;
  detail_errors: number;
  scored: number;
  unscored: number;
  score_distribution: [number, number][];
  tailored: number;
  untailored_eligible: number;
  tailor_exhausted: number;
  with_cover_letter: number;
  cover_exhausted: number;
  applied: number;
  apply_errors: number;
  ready_to_apply: number;
  by_site: [string, number][];
  [key: string]: unknown;
}

export interface PipelineRunResponse {
  accepted: boolean;
  stage: string;
  detail?: string | null;
}

export interface DeleteResult {
  deleted: number;
}

export interface UpdateResult {
  updated: boolean;
}

export interface SchedulerJob {
  id: string;
  cron: string;
  mode: "subprocess" | "direct";
  cmd: string | null;
  fn: string | null;
  timeout: number | null;
  next_run: string | null;
}
