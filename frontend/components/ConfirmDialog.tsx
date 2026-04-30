"use client";

import { useEffect, useState } from "react";

export interface ParamSpec {
  key: string;
  label: string;
  type: "number";
  default: number;
  min?: number;
  max?: number;
  step?: number;
}

export interface PendingAction {
  title: string;
  description: string;
  warning?: string;
  emphasis?: "primary" | "danger";
  params?: ParamSpec[];
  runLabel?: string;
  onConfirm: (values: Record<string, number>) => Promise<void>;
}

export function ConfirmDialog({
  pending,
  onClose,
}: {
  pending: PendingAction | null;
  onClose: () => void;
}) {
  const [values, setValues] = useState<Record<string, number>>({});
  const [running, setRunning] = useState(false);

  useEffect(() => {
    if (pending) {
      const init: Record<string, number> = {};
      for (const p of pending.params ?? []) init[p.key] = p.default;
      setValues(init);
      setRunning(false);
    }
  }, [pending]);

  useEffect(() => {
    if (!pending) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !running) onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [pending, running, onClose]);

  if (!pending) return null;

  const runLabel = pending.runLabel ?? `Run ${pending.title}`;

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4"
      onClick={() => !running && onClose()}
    >
      <div
        className="w-full max-w-md rounded-lg border border-zinc-200 bg-white p-5 shadow-xl dark:border-zinc-800 dark:bg-zinc-900"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-lg font-semibold">{pending.title}</h3>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
          {pending.description}
        </p>

        {pending.warning && (
          <div className="mt-3 rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900">
            {pending.warning}
          </div>
        )}

        {pending.params && pending.params.length > 0 && (
          <div className="mt-4 space-y-3">
            {pending.params.map((p) => (
              <label key={p.key} className="flex items-center justify-between gap-3 text-sm">
                <span className="text-zinc-700 dark:text-zinc-300">{p.label}</span>
                <input
                  type="number"
                  min={p.min}
                  max={p.max}
                  step={p.step ?? 1}
                  value={values[p.key] ?? p.default}
                  onChange={(e) =>
                    setValues((v) => ({ ...v, [p.key]: Number(e.target.value) }))
                  }
                  disabled={running}
                  className="w-24 rounded border border-zinc-300 bg-white px-2 py-1 text-right tabular-nums dark:border-zinc-700 dark:bg-zinc-900"
                />
              </label>
            ))}
          </div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            disabled={running}
            className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            Cancel
          </button>
          <button
            onClick={async () => {
              setRunning(true);
              try {
                await pending.onConfirm(values);
              } finally {
                setRunning(false);
                onClose();
              }
            }}
            disabled={running}
            className={
              "rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50 " +
              (pending.emphasis === "danger"
                ? "bg-red-600 text-white hover:bg-red-700"
                : pending.emphasis === "primary"
                  ? "bg-blue-600 text-white hover:bg-blue-700"
                  : "bg-zinc-900 text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200")
            }
          >
            {running ? "Running…" : runLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
