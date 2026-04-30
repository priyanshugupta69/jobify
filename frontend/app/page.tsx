import { JobsTable } from "@/components/JobsTable";
import { PipelineControls } from "@/components/PipelineControls";
import { SchedulerPanel } from "@/components/SchedulerPanel";
import { StatsPanel } from "@/components/StatsPanel";
import { ToastProvider } from "@/components/Toast";

export default function Home() {
  return (
    <ToastProvider>
      <main className="mx-auto max-w-7xl space-y-8 px-4 py-8">
        <header>
          <h1 className="text-2xl font-bold">job-pipeline</h1>
          <p className="text-sm text-zinc-500">
            Discover → score → tailor → apply.
          </p>
        </header>
        <StatsPanel />
        <PipelineControls />
        <SchedulerPanel />
        <JobsTable />
      </main>
    </ToastProvider>
  );
}
