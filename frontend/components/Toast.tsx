"use client";

import { createContext, useCallback, useContext, useState } from "react";

type ToastKind = "info" | "success" | "error";
interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

interface ToastCtx {
  push: (kind: ToastKind, message: string) => void;
}

const Ctx = createContext<ToastCtx | null>(null);

export function useToast() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useToast outside <ToastProvider>");
  return ctx;
}

let nextId = 1;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const push = useCallback((kind: ToastKind, message: string) => {
    const id = nextId++;
    setToasts((t) => [...t, { id, kind, message }]);
    setTimeout(() => {
      setToasts((t) => t.filter((x) => x.id !== id));
    }, 4000);
  }, []);

  return (
    <Ctx.Provider value={{ push }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={
              "rounded-md px-4 py-2 text-sm shadow-lg border " +
              (t.kind === "error"
                ? "bg-red-50 border-red-300 text-red-900"
                : t.kind === "success"
                  ? "bg-green-50 border-green-300 text-green-900"
                  : "bg-zinc-50 border-zinc-300 text-zinc-900")
            }
          >
            {t.message}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export function useAction() {
  const { push } = useToast();
  return useCallback(
    async <T,>(label: string, fn: () => Promise<T>): Promise<T | undefined> => {
      try {
        const result = await fn();
        push("success", `${label} ✓`);
        return result;
      } catch (e) {
        push("error", `${label}: ${(e as Error).message}`);
        return undefined;
      }
    },
    [push],
  );
}
