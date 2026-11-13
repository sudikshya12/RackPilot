import clsx from "clsx";
import { motion } from "framer-motion";
import { ArrowRight, Check, ClipboardCheck, Keyboard, LogOut, Network, PlayCircle, RotateCcw, Siren, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { post } from "@/api/client";
import { useAction, useDemos } from "@/api/hooks";
import type { DemoStatus } from "@/api/types";
import { Pill } from "@/components/ui/Badges";
import { ErrorState, LoadingBlock, Modal, PageHeader, Panel } from "@/components/ui/Primitives";

const ICONS: Record<string, typeof Siren> = { "incident-recovery": Siren, "server-acceptance": ClipboardCheck, "rack-lifecycle": Network };
const PROJECT_LABEL: Record<string, string> = {
  "incident-recovery": "Project 1 · Incident Detection & Recovery",
  "server-acceptance": "Project 2 · Server Intake & Acceptance",
  "rack-lifecycle": "Project 3 · Rack, Cabling & Asset Lifecycle",
};
const PREVIEW: Record<string, string[]> = {
  "restore-service": ["Establish a healthy baseline", "Introduce the fault", "Detect after 2 failed probes", "Acknowledge and investigate", "Collect evidence", "Test an incorrect hypothesis", "Apply the correct repair", "Verify recovery", "Resolve and review summary"],
  "acceptance-retest": ["Review the intake record", "Run acceptance #1", "Read the failures", "Apply labeled simulated corrections", "Re-test with a new immutable run", "Compare the runs side by side", "Open the printable report"],
  "replace-component": ["Detect the PSU fault", "Open the device and take the incident", "Review the failure evidence", "Identify a compatible spare", "Reserve it", "Record the replacement and consume", "Move the failed PSU to returns", "Re-run the health check", "Resolve and show the audit trail"],
};

function statusOf(d: DemoStatus) {
  if (!d.run) return { label: "Not started", cls: "border-line bg-canvas text-ink-2" };
  if (d.complete) return { label: "Completed", cls: "border-ok/30 bg-ok-50 text-ok" };
  if (d.run.status === "paused") return { label: `Paused · step ${(d.current ?? 0) + 1} of ${d.steps.length}`, cls: "border-warn/30 bg-warn-50 text-warn" };
  return { label: `In progress · step ${(d.current ?? 0) + 1} of ${d.steps.length}`, cls: "border-accent/30 bg-accent-50 text-accent-700" };
}

export function DemoLauncher() {
  const q = useDemos();
  const nav = useNavigate();
  const [resetOpen, setResetOpen] = useState(false);
  const [resetResult, setResetResult] = useState<{ removed: Record<string, number>; preserved: string } | null>(null);

  const start = useAction((key: string) => post<DemoStatus>(`/demos/${key}/start`), {
    success: "Demo started. Use the guide at the bottom of the screen.",
    onSuccess: (r) => { const step = r.steps?.find((s) => !s.done && s.route); nav(step?.route ?? "/"); },
  });
  const exit = useAction((key: string) => post(`/demos/${key}/exit`), { success: "Demo exited. Its simulation records were removed." });
  const reset = useAction(() => post<{ removed: Record<string, number>; preserved: string }>("/simulation/reset"), {
    success: "Simulation data reset", onSuccess: (r) => setResetResult(r),
  });

  return (
    <div className="space-y-5">
      <PageHeader title="Demonstrations"
        actions={<button className="btn-secondary" onClick={() => { setResetResult(null); setResetOpen(true); }}><Trash2 className="h-4 w-4" aria-hidden />Reset all simulation data</button>}>
        Guided 2–3 minute walkthroughs that drive the real workflows with simulated data.
      </PageHeader>

      {q.isLoading ? <LoadingBlock rows={8} /> : q.error ? <ErrorState error={q.error} retry={() => q.refetch()} /> : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {(q.data ?? []).map((d, i) => {
            const Icon = ICONS[d.project] ?? PlayCircle;
            const st = statusOf(d);
            const steps = d.steps.length ? d.steps.map((s) => ({ title: s.title, done: s.done })) : (PREVIEW[d.key] ?? []).map((t) => ({ title: t, done: false }));
            const cur = d.current !== null ? d.steps[d.current] : null;
            const active = d.run && !d.complete;
            return (
              <motion.article key={d.key} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25, delay: i * 0.06 }}
                className="panel flex flex-col overflow-hidden">
                <div className="flex items-start gap-3 border-b border-line-soft bg-gradient-to-r from-accent-50/70 to-transparent p-4">
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-nav text-accent-300"><Icon className="h-5 w-5" aria-hidden /></span>
                  <div className="min-w-0">
                    <div className="eyebrow">{PROJECT_LABEL[d.project] ?? d.project}</div>
                    <h2 className="text-[15.5px] font-semibold leading-snug text-ink">{d.title}</h2>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5"><Pill className={st.cls}>{st.label}</Pill><span className="text-[11.5px] text-ink-2">≈ {d.minutes} min</span>
                      {d.run && <span className="mono text-[11px] text-ink-3">{d.run.display_id}</span>}</div>
                  </div>
                </div>
                <div className="flex flex-1 flex-col p-4">
                  <p className="text-[12.5px] leading-relaxed text-ink-2">{d.summary}</p>
                  <ol className="mt-3 space-y-1.5" aria-label={`${d.title} steps`}>
                    {steps.map((s, k) => {
                      const isCur = d.current === k && !!d.run;
                      return (
                        <li key={s.title} className={clsx("flex items-start gap-2 text-[12.5px]", s.done ? "text-ink" : isCur ? "font-medium text-accent-700" : "text-ink-2")}>
                          <span className={clsx("mt-[1px] grid h-[18px] w-[18px] shrink-0 place-items-center rounded-full border text-[9.5px] font-bold",
                            s.done ? "border-ok bg-ok text-white" : isCur ? "border-accent text-accent" : "border-line-strong text-ink-3")}>
                            {s.done ? <Check className="h-2.5 w-2.5" aria-label="done" /> : k + 1}
                          </span>
                          <span>{s.title}{isCur && <span className="sr-only"> (current step)</span>}</span>
                        </li>
                      );
                    })}
                  </ol>
                  <div className="mt-auto flex flex-wrap gap-2 pt-4">
                    <button className="btn-primary" disabled={start.isPending} onClick={() => start.mutate(d.key)}>
                      {d.run ? <><RotateCcw className="h-4 w-4" aria-hidden />Restart</> : <><PlayCircle className="h-4 w-4" aria-hidden />Start</>}
                    </button>
                    {active && cur?.route && <button className="btn-secondary" onClick={() => nav(cur.route!)}>Continue <ArrowRight className="h-4 w-4" aria-hidden /></button>}
                    {d.run && <button className="btn-ghost" disabled={exit.isPending} onClick={() => exit.mutate(d.key)}><LogOut className="h-4 w-4" aria-hidden />Exit</button>}
                    <Link to={`/projects/${d.project}`} className="btn-ghost ml-auto">Case study</Link>
                  </div>
                </div>
              </motion.article>
            );
          })}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Demo controls" icon={<Keyboard className="h-4 w-4" />}>
          <dl className="grid grid-cols-1 gap-2 text-[12.5px] sm:grid-cols-2">
            {[
              ["Next step", "Runs the current step through the normal backend workflow. Shortcut: Shift+N."],
              ["View", "Opens the page where the current step's evidence lives."],
              ["Pause / Resume", "Freezes simulator probes, so nothing advances while you talk."],
              ["Restart", "Removes this demo's simulation records and starts again from the baseline."],
              ["Exit", "Removes this demo's simulation records and closes the guide."],
              ["Auto steps", "Baseline, fault and detection steps complete as the simulator probes every 3 s."],
            ].map(([k, v]) => (
              <div key={k} className="rounded-lg border border-line-soft p-2.5"><dt className="font-semibold text-ink">{k}</dt><dd className="text-ink-2">{v}</dd></div>
            ))}
          </dl>
          <p className="mt-3 text-[12px] text-ink-2">Reset only ever removes <b>simulation-owned</b> records and restores seed baselines. Imported samples, local-lab evidence and operator records are never touched.</p>
        </Panel>
      </div>

      <Modal open={resetOpen} onOpenChange={setResetOpen} title="Reset all simulation data" description="Removes simulated incidents, runs, reservations, returns, evidence and metrics, then restores seed baselines.">
        {resetResult ? (
          <div className="space-y-3">
            <div className="eyebrow">Removed</div>
            <ul className="grid grid-cols-2 gap-1.5 text-[12.5px]">
              {Object.entries(resetResult.removed).map(([k, v]) => <li key={k} className="flex justify-between rounded-md bg-canvas px-2 py-1"><span className="mono">{k}</span><span className="mono font-semibold">{v}</span></li>)}
            </ul>
            <p className="rounded-lg border border-ok/30 bg-ok-50 p-2.5 text-[12.5px] text-ok">{resetResult.preserved}</p>
            <div className="flex justify-end"><button className="btn-primary" onClick={() => setResetOpen(false)}>Done</button></div>
          </div>
        ) : (
          <div>
            <p className="text-[13px] text-ink">This cannot be undone. Imported samples, local-lab evidence and operator records are preserved.</p>
            <div className="mt-4 flex justify-end gap-2">
              <button className="btn-secondary" onClick={() => setResetOpen(false)}>Cancel</button>
              <button className="btn-danger" disabled={reset.isPending} onClick={() => reset.mutate()}><Trash2 className="h-4 w-4" aria-hidden />Reset simulation data</button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
