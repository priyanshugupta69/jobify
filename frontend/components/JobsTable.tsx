"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";

import {
  applyOne,
  bulkDeleteJobs,
  deleteJob,
  deleteLowScore,
  deleteSkipped,
  listJobs,
  markApplied,
  markViewed,
  tailoredResumeUrl,
  triggerRunSelected,
  updateApplicationUrl,
  type SortKey,
  type ViewedFilter,
} from "@/lib/api";
import { PIPELINE_STAGES, type Job, type PipelineStage } from "@/lib/types";
import { ConfirmDialog, type PendingAction } from "./ConfirmDialog";
import { useFilters } from "./FilterContext";
import { useAction } from "./Toast";

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function YesNo({ value }: { value: unknown }) {
  return value ? (
    <span className="text-green-700 dark:text-green-400">✓</span>
  ) : (
    <span className="text-zinc-400">—</span>
  );
}

function useDebounced<T>(value: T, ms = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return debounced;
}

export function JobsTable() {
  const [stage, setStage] = useState<PipelineStage>("scored");
  const [minScore, setMinScore] = useState<string>("");
  const [limit, setLimit] = useState<string>("100");
  const [threshold, setThreshold] = useState<string>("5");
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [viewedFilter, setViewedFilter] = useState<ViewedFilter>("all");
  const [sort, setSort] = useState<SortKey>("score");
  // Track URLs marked viewed *this session* so the row visual updates
  // immediately without waiting for a refresh round-trip.
  const [recentlyViewed, setRecentlyViewed] = useState<Set<string>>(new Set());
  const { site, setSite } = useFilters();
  const run = useAction();

  // Debounce text inputs so typing "10" doesn't fire two requests.
  const debouncedMinScore = useDebounced(minScore);
  const debouncedLimit = useDebounced(limit);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const ms = debouncedMinScore ? Number(debouncedMinScore) : null;
      const lim = debouncedLimit ? Number(debouncedLimit) : 100;
      setJobs(
        await listJobs({ stage, minScore: ms, limit: lim, site, viewed: viewedFilter, sort }),
      );
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [stage, debouncedMinScore, debouncedLimit, site, viewedFilter, sort]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Reset selection / expansion whenever the underlying job list changes.
  useEffect(() => {
    setSelected(new Set());
    setExpanded(new Set());
  }, [jobs]);

  const allSelected = useMemo(
    () => !!jobs && jobs.length > 0 && jobs.every((j) => selected.has(j.url)),
    [jobs, selected],
  );

  const toggleOne = (url: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });
  };

  const toggleAll = () => {
    if (!jobs) return;
    setSelected(allSelected ? new Set() : new Set(jobs.map((j) => j.url)));
  };

  const toggleExpand = (url: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });
  };

  const onMarkApplied = async (url: string) => {
    await run("Mark applied", () => markApplied(url));
    refresh();
  };

  const onDelete = async (url: string) => {
    if (!confirm(`Delete job?\n${url}`)) return;
    await run("Delete job", () => deleteJob(url));
    refresh();
  };

  const onDeleteSelected = async () => {
    const urls = Array.from(selected);
    if (urls.length === 0) return;
    if (!confirm(`Delete ${urls.length} selected job${urls.length === 1 ? "" : "s"}?`))
      return;
    await run(`Delete ${urls.length} selected`, () => bulkDeleteJobs(urls));
    refresh();
  };

  const onRunPipelineSelected = () => {
    const urls = Array.from(selected);
    if (urls.length === 0) return;
    setPending({
      title: `Run pipeline on ${urls.length} selected`,
      description:
        "Extracts apply URL → tailors resume + cover letter → auto-applies. " +
        "Apply runs sequentially with 5–10 min spacing between submits. " +
        "Selected jobs with fit_score < 8 will be skipped at the tailor step.",
      warning:
        "Hits LinkedIn, Gemini, and Anthropic. Will actually click Submit unless " +
        "AUTO_APPLY_DRY_RUN=true (default). Auto-apply requires AUTO_APPLY_ENABLED=true; " +
        "otherwise the apply phase falls back to marking jobs needs_manual.",
      emphasis: "primary",
      runLabel: `Run on ${urls.length}`,
      onConfirm: async () => {
        await run(`Run pipeline on ${urls.length}`, () => triggerRunSelected({ urls }));
      },
    });
  };

  const onApplyOne = async (url: string) => {
    await run("Apply one", () => applyOne(url));
    refresh();
  };

  const onJobLinkClick = (url: string) => {
    // Optimistically mark as viewed so the row visual updates immediately;
    // fire-and-forget the API call so we don't delay the user opening the
    // tab. Errors are swallowed — worst case the row syncs on next refresh.
    setRecentlyViewed((prev) => {
      if (prev.has(url)) return prev;
      const next = new Set(prev);
      next.add(url);
      return next;
    });
    markViewed(url).catch(() => { /* tolerate transient API failures */ });
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
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Jobs</h2>
        {loading && (
          <span className="text-xs text-zinc-500">loading…</span>
        )}
      </div>

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
        <label className="flex flex-col">
          <span className="text-xs text-zinc-500">Viewed</span>
          <select
            value={viewedFilter}
            onChange={(e) => setViewedFilter(e.target.value as ViewedFilter)}
            className="rounded border border-zinc-300 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
            title="Filter by whether you've opened the job link from the dashboard"
          >
            <option value="all">all</option>
            <option value="unviewed">unviewed</option>
            <option value="viewed">viewed</option>
          </select>
        </label>
        <label className="flex flex-col">
          <span className="text-xs text-zinc-500">Sort</span>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            className="rounded border border-zinc-300 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
            title="Sort order for the results"
          >
            <option value="score">score (default)</option>
            <option value="newest">newest discovered</option>
            <option value="oldest">oldest discovered</option>
            <option value="recently_scored">recently scored</option>
            <option value="recently_tailored">recently tailored</option>
            <option value="recently_viewed">recently viewed</option>
            <option value="recently_applied">recently applied</option>
          </select>
        </label>
        {site && (
          <div className="flex flex-col">
            <span className="text-xs text-zinc-500">Site</span>
            <button
              onClick={() => setSite(null)}
              className="flex items-center gap-1 rounded border border-blue-400 bg-blue-50 px-2 py-1 text-blue-900 hover:bg-blue-100 dark:border-blue-700 dark:bg-blue-950 dark:text-blue-200 dark:hover:bg-blue-900"
              title="Clear site filter"
            >
              {site} <span className="text-xs">×</span>
            </button>
          </div>
        )}

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

      {selected.size > 0 && (
        <div className="flex items-center justify-between rounded-md border border-blue-300 bg-blue-50 px-3 py-2 text-sm dark:border-blue-900 dark:bg-blue-950">
          <span className="text-blue-900 dark:text-blue-200">
            {selected.size} selected
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setSelected(new Set())}
              className="rounded border border-zinc-300 bg-white px-2 py-0.5 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
            >
              Clear
            </button>
            <button
              onClick={onRunPipelineSelected}
              className="rounded border border-blue-600 bg-blue-600 px-2 py-0.5 text-xs font-medium text-white hover:bg-blue-700"
              title="Extract URLs → tailor resume/cover → auto-apply"
            >
              Run pipeline on {selected.size}
            </button>
            <button
              onClick={onDeleteSelected}
              className="rounded border border-red-300 bg-white px-2 py-0.5 text-xs font-medium text-red-700 hover:bg-red-50"
            >
              Delete {selected.size} selected
            </button>
          </div>
        </div>
      )}

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
                <th className="px-3 py-2 font-medium w-8">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={toggleAll}
                    aria-label="Select all"
                  />
                </th>
                <th className="px-2 py-2 font-medium w-6"></th>
                <th className="px-3 py-2 font-medium">Title</th>
                <th className="px-3 py-2 font-medium">Site</th>
                <th className="px-3 py-2 font-medium">Location</th>
                <th className="px-3 py-2 font-medium">Salary</th>
                <th className="px-3 py-2 font-medium">Score</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium" title="Open tailored resume PDF">Resume</th>
                <th className="px-3 py-2 font-medium" title="External application URL extracted">App URL</th>
                <th className="px-3 py-2 font-medium">Scored at</th>
                <th className="px-3 py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {jobs.map((j) => {
                const isExpanded = expanded.has(j.url);
                const isViewed = !!j.viewed_at || recentlyViewed.has(j.url);
                return (
                  <Fragment key={j.url}>
                    <tr
                      className={
                        "align-top" + (isViewed ? " text-zinc-500 dark:text-zinc-500" : "")
                      }
                    >
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={selected.has(j.url)}
                          onChange={() => toggleOne(j.url)}
                          aria-label={`Select ${j.title ?? j.url}`}
                        />
                      </td>
                      <td className="px-2 py-2">
                        <button
                          onClick={() => toggleExpand(j.url)}
                          aria-label={isExpanded ? "Collapse" : "Expand"}
                          className="rounded px-1 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                        >
                          {isExpanded ? "▾" : "▸"}
                        </button>
                      </td>
                      <td className="px-3 py-2 max-w-md">
                        <a
                          href={j.url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={() => onJobLinkClick(j.url)}
                          onAuxClick={(e) => {
                            // middle-click also opens the link in a new tab
                            if (e.button === 1) onJobLinkClick(j.url);
                          }}
                          className={
                            "hover:underline break-words " +
                            (isViewed
                              ? "text-blue-500/70 visited:text-purple-500/70"
                              : "text-blue-600")
                          }
                        >
                          {j.title ?? j.url}
                        </a>
                      </td>
                      <td className="px-3 py-2 text-xs">
                        {j.site ? (
                          <button
                            onClick={() => setSite(j.site!)}
                            className="rounded-full bg-zinc-100 px-2 py-0.5 text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
                            title={`Filter by ${j.site}`}
                          >
                            {j.site}
                          </button>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="px-3 py-2 text-xs">{j.location ?? "—"}</td>
                      <td className="px-3 py-2 text-xs">{j.salary ?? "—"}</td>
                      <td className="px-3 py-2 text-xs tabular-nums">
                        {j.fit_score ?? "—"}
                      </td>
                      <td className="px-3 py-2 text-xs">
                        {j.apply_status ?? "—"}
                      </td>
                      <td className="px-3 py-2 text-xs">
                        {j.tailored_resume_path ? (
                          <a
                            href={tailoredResumeUrl(j.url)}
                            target="_blank"
                            rel="noreferrer"
                            className="text-blue-600 hover:underline"
                            title={j.tailored_resume_path}
                          >
                            View
                          </a>
                        ) : (
                          <span className="text-zinc-400">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-xs"><YesNo value={j.application_url} /></td>
                      <td className="px-3 py-2 text-xs whitespace-nowrap">{formatDate(j.scored_at)}</td>
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
                    {isExpanded && (
                      <tr className="bg-zinc-50/50 dark:bg-zinc-900/40">
                        <td colSpan={12} className="px-6 py-4">
                          <JobDetails job={j} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog pending={pending} onClose={() => setPending(null)} />
    </section>
  );
}

function JobDetails({ job }: { job: Job }) {
  const description = job.full_description || job.description || "";
  return (
    <div className="grid grid-cols-1 gap-4 text-xs md:grid-cols-3">
      <div className="md:col-span-2 space-y-3">
        <Field label="Description">
          {description ? (
            <pre className="whitespace-pre-wrap break-words font-sans text-xs text-zinc-700 dark:text-zinc-300 max-h-96 overflow-y-auto">
              {description}
            </pre>
          ) : (
            <span className="text-zinc-400">—</span>
          )}
        </Field>
        {job.score_reasoning && (
          <Field label="Score reasoning">
            <pre className="whitespace-pre-wrap break-words font-sans text-xs text-zinc-700 dark:text-zinc-300">
              {job.score_reasoning}
            </pre>
          </Field>
        )}
      </div>
      <div className="space-y-2">
        <Field label="Application URL">
          {job.application_url ? (
            <a
              href={job.application_url}
              target="_blank"
              rel="noreferrer"
              className="text-blue-600 hover:underline break-all"
            >
              {job.application_url}
            </a>
          ) : (
            <span className="text-zinc-400">—</span>
          )}
        </Field>
        <Field label="Tailored resume">
          {job.tailored_resume_path ? (
            <a
              href={tailoredResumeUrl(job.url)}
              target="_blank"
              rel="noreferrer"
              className="break-all text-blue-600 hover:underline"
            >
              {job.tailored_resume_path}
            </a>
          ) : (
            <span className="text-zinc-400">—</span>
          )}
        </Field>
        <Field label="Cover letter">
          {job.cover_letter_path ? (
            <code className="break-all text-zinc-700 dark:text-zinc-300">
              {job.cover_letter_path}
            </code>
          ) : (
            <span className="text-zinc-400">—</span>
          )}
        </Field>
        <Field label="Discovered at">{formatDate(job.discovered_at)}</Field>
        <Field label="Detail scraped at">{formatDate(job.detail_scraped_at)}</Field>
        <Field label="Tailored at">{formatDate(job.tailored_at)}</Field>
        <Field label="Applied at">{formatDate(job.applied_at)}</Field>
        <Field label="Last attempted at">{formatDate(job.last_attempted_at)}</Field>
        {job.apply_error && (
          <Field label="Apply error">
            <span className="text-red-700 dark:text-red-400">{job.apply_error}</span>
          </Field>
        )}
        <div className="flex gap-3 pt-1 text-zinc-500">
          <span>tailor_attempts: {job.tailor_attempts ?? 0}</span>
          <span>cover_attempts: {job.cover_attempts ?? 0}</span>
          <span>apply_attempts: {job.apply_attempts ?? 0}</span>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-0.5 text-[10px] uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <div>{children}</div>
    </div>
  );
}
