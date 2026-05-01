"use client";

import { useState } from "react";

import {
  sendDailyReport,
  triggerBatch,
  triggerCleanup,
  triggerDiscover,
  triggerExtractUrls,
  triggerFull,
  triggerPostScoreCleanup,
  triggerScore,
  triggerTailor,
} from "@/lib/api";
import { ConfirmDialog, type PendingAction } from "./ConfirmDialog";
import { useAction } from "./Toast";

interface ButtonSpec {
  key: string;
  label: string;
  emphasis?: "primary" | "danger";
  build: (run: ReturnType<typeof useAction>) => PendingAction;
}

// Button order matches the actual pipeline flow:
// Discover → Cleanup → Score → Post-score cleanup → Extract URLs →
// Tailor → Batch (preview) → Full pipeline → Send daily report
const BUTTONS: ButtonSpec[] = [
  {
    key: "discover",
    label: "Discover",
    build: (run) => ({
      title: "Discover",
      description:
        "Scrape job sites for new postings matching your search and enrich with detail pages. Inserts new rows into the database. Runs in the background — minutes.",
      warning: "Hits external sites (LinkedIn etc).",
      params: [{ key: "workers", label: "Workers", type: "number", default: 3, min: 1, max: 8 }],
      onConfirm: async (v) => {
        await run("Discover", () => triggerDiscover(v.workers));
      },
    }),
  },
  {
    key: "cleanup",
    label: "Cleanup",
    build: (run) => ({
      title: "Cleanup",
      description:
        "Delete jobs that are clearly invalid (broken URLs, scrape errors, blank descriptions). Idempotent and safe.",
      warning: "Deletes rows.",
      emphasis: "danger",
      onConfirm: async () => {
        await run("Cleanup", () => triggerCleanup());
      },
    }),
  },
  {
    key: "score",
    label: "Score",
    build: (run) => ({
      title: "Score",
      description:
        "Use Gemini to rate every unscored job 1–10 against your profile. Then runs post-score cleanup. LLM-bound — minutes.",
      warning: "Calls the Gemini API (uses GEMINI_API_KEY credits).",
      onConfirm: async () => {
        await run("Score", () => triggerScore());
      },
    }),
  },
  {
    key: "post-score-cleanup",
    label: "Post-score cleanup",
    build: (run) => ({
      title: "Post-score cleanup",
      description:
        "Delete scored jobs below the auto-cull threshold and jobs where scoring permanently failed.",
      warning: "Deletes rows.",
      emphasis: "danger",
      onConfirm: async () => {
        await run("Post-score cleanup", () => triggerPostScoreCleanup());
      },
    }),
  },
  {
    key: "extract-urls",
    label: "Extract URLs",
    build: (run) => ({
      title: "Extract URLs",
      description:
        "Open each LinkedIn posting in headless Chrome and pull out the external company-ATS apply URL. Slow — Playwright per job.",
      warning: "Launches a headless browser; uses memory.",
      params: [{ key: "limit", label: "Limit", type: "number", default: 50, min: 1, max: 500 }],
      onConfirm: async (v) => {
        await run("Extract URLs", () => triggerExtractUrls({ limit: v.limit }));
      },
    }),
  },
  {
    key: "tailor",
    label: "Tailor",
    build: (run) => ({
      title: "Tailor",
      description:
        "For jobs above the score threshold, ask Gemini to rewrite resume + cover letter and convert to PDF. Slow — 30s to 2min per job.",
      warning: "Calls the Gemini API.",
      params: [
        { key: "min_score", label: "Min score", type: "number", default: 8, min: 1, max: 10 },
        { key: "workers", label: "Workers", type: "number", default: 3, min: 1, max: 8 },
      ],
      onConfirm: async (v) => {
        await run("Tailor", () =>
          triggerTailor({ min_score: v.min_score, workers: v.workers }),
        );
      },
    }),
  },
  {
    key: "batch",
    label: "Batch (preview)",
    build: (run) => ({
      title: "Batch (preview)",
      description:
        "Pick top-N high-scoring jobs ready for human review and format as a Telegram message — but DOES NOT send it. Safe preview.",
      onConfirm: async () => {
        await run("Batch preview", () => triggerBatch({ skip_send: true }));
      },
    }),
  },
  {
    key: "full",
    label: "Full pipeline",
    emphasis: "primary",
    build: (run) => ({
      title: "Full pipeline",
      description:
        "Run Discover → Score → Tailor → Extract URLs end-to-end as one daily job. The big one — tens of minutes.",
      warning: "Hits LinkedIn AND Gemini AND launches Chrome. Make sure you really want this.",
      emphasis: "primary",
      onConfirm: async () => {
        await run("Full pipeline", () => triggerFull());
      },
    }),
  },
  {
    key: "send-report",
    label: "Send daily report",
    build: (run) => ({
      title: "Send daily report",
      description:
        "Build the daily-stats summary and send it to your Telegram chat right now.",
      warning: "Sends a real Telegram message to TELEGRAM_CHAT_ID.",
      emphasis: "primary",
      runLabel: "Send now",
      onConfirm: async () => {
        await run("Send daily report", () => sendDailyReport());
      },
    }),
  },
];

export function PipelineControls() {
  const run = useAction();
  const [pending, setPending] = useState<PendingAction | null>(null);

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Pipeline</h2>
      <p className="text-xs text-zinc-500">
        Click a button to open a confirmation dialog. Nothing runs until you click <span className="font-medium">Run</span> there.
      </p>
      <div className="flex flex-wrap gap-2">
        {BUTTONS.map((b) => (
          <button
            key={b.key}
            onClick={() => setPending(b.build(run))}
            className={
              "rounded-md px-3 py-1.5 text-sm font-medium border transition-colors " +
              (b.emphasis === "primary"
                ? "bg-blue-600 text-white border-blue-600 hover:bg-blue-700"
                : b.emphasis === "danger"
                  ? "bg-white text-red-700 border-red-300 hover:bg-red-50"
                  : "bg-white text-zinc-900 border-zinc-300 hover:bg-zinc-50 dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800")
            }
          >
            {b.label}…
          </button>
        ))}
      </div>

      <ConfirmDialog pending={pending} onClose={() => setPending(null)} />
    </section>
  );
}
