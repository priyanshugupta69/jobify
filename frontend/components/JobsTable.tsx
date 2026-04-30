"use client";

import { useCallback, useEffect, useState } from "react";

import {
  applyOne,
  deleteJob,
  deleteLowScore,
  deleteSkipped,
  listJobs,
  markApplied,
  updateApplicationUrl,
} from "@/lib/api";
import { PIPELINE_STAGES, type Job, type PipelineStage } from "@/lib/types";
import { useAction } from "./Toast";

export function JobsTable() {
  const [stage, setStage] = useState<PipelineStage>("scored");
  const [minScore, setMinScore] = useState<string>("");
  const [limit, setLimit] = useState<string>("100");
  const [threshold, setThreshold] = useState<string>("5");
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const run = useAction();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const ms = minScore ? Number(minScore) : null;
      const lim = limit ? Number(limit) : 100;
      setJobs(
        await listJobs({ stage, minScore: ms, limit: lim }),
      );
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [stage, minScore, limit]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const onMarkApplied = async (url: string) => {
    await run("Mark applied", () => markApplied(url));
    refresh();
  };

  const onDelete = async (url: string) => {
    if (!confirm(`Delete job?\n${url}`)) return;
    await run("Delete job", () => deleteJob(url));
    refresh();
  };

  const onApplyOne = async (url: string) => {
    await run("Apply one", () => applyOne(url));
    refresh();
  };

  const onEditAppUrl = async (job: Job) => {
    const next = prompt(
      "Application URL (empty to clear):",
      job.application_url ?? "",
    );
    if (next === null) return;
    await run("Update application URL", () =>
      updateApplicationUrl(job.url, next || null),
    );
    refresh();
  };

  const onDeleteLowScore = async () => {
    const t = Number(threshold);
    if (!Number.isFinite(t) || t < 1 || t > 10) {
      alert("Threshold must be 1–10");
      return;
    }
    if (!confirm(`Delete all jobs with fit_score < ${t}?`)) return;
    await run("Delete low-score", () => deleteLowScore(t));
    refresh();
  };

  const onDeleteSkipped = async () => {
    if (!confirm("Delete all skipped jobs?")) return;
    await run("Delete skipped", () => deleteSkipped());
    refresh();
  };

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Jobs</h2>

      <div className="flex flex-wrap items-end gap-3 text-sm">
        <label className="flex flex-col">
          <span className="text-xs text-zinc-500">Stage</span>
          <select
            value={stage}
            onChange={(e) => setStage(e.target.value as PipelineStage)}
            className="rounded border border-zinc-300 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
          >
            {PIPELINE_STAGES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col">
          <span className="text-xs text-zinc-500">Min score</span>
          <input
            type="number"
            min={1}
            max={10}
            value={minScore}
            onChange={(e) => setMinScore(e.target.value)}
            placeholder="any"
            className="w-24 rounded border border-zinc-300 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
          />
        </label>
        <label className="flex flex-col">
          <span className="text-xs text-zinc-500">Limit</span>
          <input
            type="number"
            min={1}
            max={1000}
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
            className="w-24 rounded border border-zinc-300 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
          />
        </label>
        <button
          onClick={refresh}
          disabled={loading}
          className="rounded border border-zinc-300 bg-white px-3 py-1 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
        >
          {loading ? "loading…" : "Apply filters"}
        </button>

        <div className="ml-auto flex items-end gap-2 text-xs">
          <label className="flex flex-col">
            <span className="text-zinc-500">Low-score threshold</span>
            <input
              type="number"
              min={1}
              max={10}
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              className="w-20 rounded border border-zinc-300 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
            />
          </label>
          <button
            onClick={onDeleteLowScore}
            className="rounded border border-red-300 bg-white px-2 py-1 text-red-700 hover:bg-red-50"
          >
            Delete &lt; threshold
          </button>
          <button
            onClick={onDeleteSkipped}
            className="rounded border border-red-300 bg-white px-2 py-1 text-red-700 hover:bg-red-50"
          >
            Delete skipped
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-900">
          {error}
        </div>
      )}

      {jobs && jobs.length === 0 && (
        <p className="text-sm text-zinc-500">No jobs match these filters.</p>
      )}

      {jobs && jobs.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 dark:bg-zinc-900">
              <tr className="text-left text-xs uppercase tracking-wide text-zinc-500">
                <th className="px-3 py-2 font-medium">Title</th>
                <th className="px-3 py-2 font-medium">Site</th>
                <th className="px-3 py-2 font-medium">Location</th>
                <th className="px-3 py-2 font-medium">Score</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {jobs.map((j) => (
                <tr key={j.url} className="align-top">
                  <td className="px-3 py-2 max-w-md">
                    <a
                      href={j.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-600 hover:underline break-words"
                    >
                      {j.title ?? j.url}
                    </a>
                  </td>
                  <td className="px-3 py-2 text-xs">{j.site ?? "—"}</td>
                  <td className="px-3 py-2 text-xs">{j.location ?? "—"}</td>
                  <td className="px-3 py-2 text-xs tabular-nums">
                    {j.fit_score ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {j.apply_status ?? "—"}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap justify-end gap-1 text-xs">
                      <button
                        onClick={() => onEditAppUrl(j)}
                        className="rounded border border-zinc-300 bg-white px-2 py-0.5 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
                      >
                        Edit URL
                      </button>
                      <button
                        onClick={() => onApplyOne(j.url)}
                        className="rounded border border-zinc-300 bg-white px-2 py-0.5 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
                      >
                        Apply
                      </button>
                      <button
                        onClick={() => onMarkApplied(j.url)}
                        className="rounded border border-green-300 bg-white px-2 py-0.5 text-green-700 hover:bg-green-50"
                      >
                        Mark applied
                      </button>
                      <button
                        onClick={() => onDelete(j.url)}
                        className="rounded border border-red-300 bg-white px-2 py-0.5 text-red-700 hover:bg-red-50"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
