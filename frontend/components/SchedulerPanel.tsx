"use client";

import { useCallback, useEffect, useState } from "react";

import { listSchedulerJobs } from "@/lib/api";
import type { SchedulerJob } from "@/lib/types";

function formatNextRun(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

export function SchedulerPanel() {
  const [jobs, setJobs] = useState<SchedulerJob[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setJobs(await listSchedulerJobs());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Scheduler</h2>
        <button
          onClick={refresh}
          disabled={loading}
          className="text-xs text-zinc-500 hover:text-zinc-900 disabled:opacity-50"
        >
          {loading ? "refreshing…" : "refresh"}
        </button>
      </div>

      {error && (
        <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-900">
          {error}
        </div>
      )}

      {jobs && jobs.length === 0 && (
        <p className="text-sm text-zinc-500">
          No scheduler jobs registered (is <code>SCHEDULER_ENABLED</code> set?).
        </p>
      )}

      {jobs && jobs.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 dark:bg-zinc-900">
              <tr className="text-left text-xs uppercase tracking-wide text-zinc-500">
                <th className="px-3 py-2 font-medium">ID</th>
                <th className="px-3 py-2 font-medium">Cron</th>
                <th className="px-3 py-2 font-medium">Mode</th>
                <th className="px-3 py-2 font-medium">Next run</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {jobs.map((j) => (
                <tr key={j.id}>
                  <td className="px-3 py-2 font-mono text-xs">{j.id}</td>
                  <td className="px-3 py-2 font-mono text-xs">{j.cron}</td>
                  <td className="px-3 py-2 text-xs">{j.mode}</td>
                  <td className="px-3 py-2 text-xs">
                    {formatNextRun(j.next_run)}
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
