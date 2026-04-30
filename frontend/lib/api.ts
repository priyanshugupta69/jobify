import type {
  DeleteResult,
  Job,
  PipelineRunResponse,
  PipelineStage,
  SchedulerJob,
  StatsResponse,
  UpdateResult,
} from "./types";

const BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}

const enc = (url: string) => encodeURI(url);

export const getStats = () => request<StatsResponse>("/stats");

export interface ListJobsParams {
  stage: PipelineStage;
  minScore?: number | null;
  limit?: number;
}
export function listJobs({
  stage,
  minScore,
  limit = 100,
}: ListJobsParams): Promise<Job[]> {
  const qs = new URLSearchParams({ stage, limit: String(limit) });
  if (minScore != null) qs.set("min_score", String(minScore));
  return request<Job[]>(`/jobs?${qs.toString()}`);
}

export const deleteJob = (url: string) =>
  request<DeleteResult>(`/jobs/${enc(url)}`, { method: "DELETE" });

export const markApplied = (url: string) =>
  request<UpdateResult>(`/jobs/${enc(url)}/applied`, { method: "PATCH" });

export const updateApplicationUrl = (
  url: string,
  application_url: string | null,
) =>
  request<UpdateResult>(`/jobs/${enc(url)}/application-url`, {
    method: "PATCH",
    body: JSON.stringify({ application_url }),
  });

export const deleteLowScore = (threshold: number) =>
  request<DeleteResult>(`/jobs/low-score?threshold=${threshold}`, {
    method: "DELETE",
  });

export const deleteSkipped = () =>
  request<DeleteResult>(`/jobs/skipped`, { method: "DELETE" });

export const triggerDiscover = (workers = 3) =>
  request<PipelineRunResponse>(`/pipeline/discover?workers=${workers}`, {
    method: "POST",
  });

export const triggerScore = () =>
  request<PipelineRunResponse>(`/pipeline/score`, { method: "POST" });

export interface TailorOpts {
  urls?: string[];
  min_score?: number;
  workers?: number;
}
export const triggerTailor = (opts: TailorOpts = {}) =>
  request<PipelineRunResponse>(`/pipeline/tailor`, {
    method: "POST",
    body: JSON.stringify(opts),
  });

export interface ExtractUrlsOpts {
  urls?: string[];
  limit?: number;
}
export const triggerExtractUrls = (opts: ExtractUrlsOpts = {}) =>
  request<PipelineRunResponse>(`/pipeline/extract-urls`, {
    method: "POST",
    body: JSON.stringify(opts),
  });

export const triggerFull = () =>
  request<PipelineRunResponse>(`/pipeline/full`, { method: "POST" });

export const triggerCleanup = () =>
  request<Record<string, unknown>>(`/pipeline/cleanup`, { method: "POST" });

export const triggerPostScoreCleanup = () =>
  request<Record<string, unknown>>(`/pipeline/cleanup/post-score`, {
    method: "POST",
  });

export interface BatchOpts {
  limit?: number;
  min_score?: number;
  skip_send?: boolean;
}
export const triggerBatch = (opts: BatchOpts = {}) =>
  request<Record<string, unknown>>(`/pipeline/batch`, {
    method: "POST",
    body: JSON.stringify(opts),
  });

export const applyOne = (url: string) =>
  request<Record<string, unknown>>(`/pipeline/apply/${enc(url)}`, {
    method: "POST",
  });

export const getDailyReport = () =>
  request<Record<string, unknown>>(`/pipeline/report/daily`);

export const sendDailyReport = () =>
  request<Record<string, unknown>>(`/pipeline/report/daily/send`, {
    method: "POST",
  });

export const listSchedulerJobs = () =>
  request<SchedulerJob[]>(`/scheduler/jobs`);

export const runScheduleNow = (id: string) =>
  request<Record<string, unknown>>(`/scheduler/run/${encodeURIComponent(id)}`, {
    method: "POST",
  });
