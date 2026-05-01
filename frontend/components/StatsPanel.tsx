"use client";

import { useCallback, useEffect, useState } from "react";

import { getStats } from "@/lib/api";
import type { StatsResponse } from "@/lib/types";
import { useFilters } from "./FilterContext";

const REFRESH_MS = 30_000;

function Card({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="text-xs uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

export function StatsPanel() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { site: activeSite, toggleSite } = useFilters();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setStats(await getStats());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(id);
  }, [refresh]);

  return (
    <section className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Stats</h2>
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

      {stats && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <Card label="Total" value={stats.total} />
            <Card label="Scored" value={stats.scored} />
            <Card label="Tailored" value={stats.tailored} />
            <Card label="Applied" value={stats.applied} />
            <Card label="Ready to apply" value={stats.ready_to_apply} />
            <Card label="Apply errors" value={stats.apply_errors} />
          </div>

          {stats.score_distribution.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-medium text-zinc-600">
                Score distribution
              </h3>
              <div className="flex items-end gap-1 h-20">
                {stats.score_distribution.map(([score, count]) => {
                  const max = Math.max(
                    ...stats.score_distribution.map(([, c]) => c),
                  );
                  const h = max > 0 ? (count / max) * 100 : 0;
                  return (
                    <div
                      key={score}
                      className="flex-1 flex flex-col items-center justify-end"
                      title={`score ${score}: ${count} jobs`}
                    >
                      <div
                        className="w-full bg-blue-500/80 rounded-t"
                        style={{ height: `${h}%`, minHeight: count ? 2 : 0 }}
                      />
                      <div className="mt-1 text-[10px] text-zinc-500">
                        {score}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {stats.by_site.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-medium text-zinc-600">
                By site
                <span className="ml-2 text-[10px] font-normal text-zinc-400">
                  (click to filter the table below)
                </span>
              </h3>
              <div className="flex flex-wrap gap-2 text-xs">
                {stats.by_site.map(([site, count]) => {
                  const isActive = activeSite?.toLowerCase() === site.toLowerCase();
                  return (
                    <button
                      key={site}
                      onClick={() => toggleSite(site)}
                      className={
                        "rounded-full px-2 py-0.5 transition-colors " +
                        (isActive
                          ? "bg-blue-600 text-white hover:bg-blue-700"
                          : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700")
                      }
                      title={
                        isActive
                          ? `Clear filter (currently ${site})`
                          : `Filter table by ${site}`
                      }
                    >
                      {site}: <span className="font-medium">{count}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
