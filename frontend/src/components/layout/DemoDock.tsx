import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronUp, Eye, LogOut, Pause, Play, RotateCcw, SkipForward, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { post } from "@/api/client";
import { useAction } from "@/api/hooks";
import type { DemoStatus } from "@/api/types";
import { useToast } from "@/components/ui/Toast";

const dockBtn = "btn h-8 border border-white/10 px-2.5 text-nav-text hover:bg-white/[0.06] hover:text-white";

export function DemoDock({ demo, onDismiss }: { demo: DemoStatus; onDismiss: () => void }) {
  const nav = useNavigate();
  const toast = useToast();
  const [expanded, setExpanded] = useState(false);
  const paused = demo.run?.status === "paused";
  const cur = demo.current !== null ? demo.steps[demo.current] : null;
  const doneCount = demo.steps.filter((s) => s.done).length;

  const next = useAction(() => post<{ message: string; route?: string }>(`/demos/${demo.key}/next`), {
    onSuccess: (r) => { toast.push({ tone: "info", title: r.message }); if (r.route) nav(r.route); },
  });
  const pause = useAction(() => post(`/demos/${demo.key}/${paused ? "resume" : "pause"}`), { success: paused ? "Demo resumed" : "Demo paused" });
  const restart = useAction(() => post(`/demos/${demo.key}/start`), { success: "Demo restarted" });
  const exit = useAction(() => post(`/demos/${demo.key}/exit`), { success: "Demo exited. Its simulation records were removed.", onSuccess: () => nav("/demo") });

  useEffect(() => {
    if (demo.complete) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.shiftKey && e.key.toLowerCase() === "n" && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) next.mutate();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [next, demo.complete]);

  if (demo.complete) {
    const results = [...demo.steps].reverse().find((s) => s.route)?.route ?? "/";
    return (
      <motion.div role="region" aria-label="Guided demonstration controls" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 16 }}
        transition={{ duration: 0.2 }} className="no-print fixed bottom-4 right-4 z-40 w-[min(340px,calc(100vw-2rem))] rounded-xl border border-line bg-white p-3.5 shadow-lift">
        <div className="flex items-start gap-2.5">
          <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-ok-50 text-ok"><Check className="h-3.5 w-3.5" aria-hidden /></span>
          <div className="min-w-0 flex-1">
            <div className="text-[13px] font-semibold text-ink">Demonstration complete</div>
            <div className="truncate text-[12px] text-ink-2">{demo.title}</div>
          </div>
          <button className="rounded p-1 text-ink-3 hover:bg-canvas hover:text-ink" onClick={onDismiss} aria-label="Close demo summary"><X className="h-3.5 w-3.5" /></button>
        </div>
        <div className="mt-3 flex gap-2 pl-7">
          <button className="btn-primary btn-sm" onClick={() => nav(results)}>View results</button>
          <button className="btn-secondary btn-sm" onClick={onDismiss}>Close</button>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div className="no-print fixed inset-x-3 bottom-3 z-40 lg:left-[244px]" initial={{ y: 80, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 80, opacity: 0 }}
      transition={{ duration: 0.22, ease: [0.2, 0.8, 0.2, 1] }} role="region" aria-label="Guided demonstration controls">
      <div className="dark-surface mx-auto max-w-[1120px] overflow-hidden rounded-xl border border-white/10 bg-nav text-nav-text shadow-[0_12px_40px_-12px_rgba(16,24,39,0.55)]">
        <AnimatePresence initial={false}>
          {expanded && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden border-b border-white/10">
              <div className="grid grid-cols-1 gap-4 p-4 md:grid-cols-[1fr_1fr]">
                <div>
                  {cur && <><div className="text-[13px] font-semibold text-white">{cur.title}</div><p className="mt-1 text-[12.5px] leading-relaxed">{cur.body}</p>
                    {cur.auto && <p className="mt-1.5 text-[12px] text-accent-300">Completes automatically as the simulator runs.</p>}</>}
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {cur?.route && <button className={dockBtn} onClick={() => nav(cur.route!)}><Eye className="h-3.5 w-3.5" aria-hidden />View</button>}
                    <button className={dockBtn} onClick={() => restart.mutate()}><RotateCcw className="h-3.5 w-3.5" aria-hidden />Restart</button>
                    <span className="self-center text-[11px] text-nav-muted">Shift+N advances</span>
                  </div>
                </div>
                <ol className="grid grid-cols-1 gap-0.5 sm:grid-cols-2 md:grid-cols-1 lg:grid-cols-2">
                  {demo.steps.map((s, i) => (
                    <li key={s.key}>
                      <button disabled={!s.route} onClick={() => s.route && nav(s.route)}
                        className={clsx("flex w-full items-start gap-2 rounded-md px-1.5 py-1 text-left text-[12px] hover:bg-white/[0.05]", i === demo.current ? "text-white" : s.done ? "text-nav-text" : "text-nav-muted")}>
                        <span className={clsx("mt-[1px] grid h-4 w-4 shrink-0 place-items-center rounded-full border text-[9px] font-bold",
                          s.done ? "border-accent-300 bg-accent-300 text-nav" : i === demo.current ? "border-white" : "border-white/20")}>{s.done ? <Check className="h-2.5 w-2.5" /> : i + 1}</span>
                        <span className="truncate">{s.title}</span>
                      </button>
                    </li>
                  ))}
                </ol>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        <div className="flex items-center gap-3 px-3 py-2">
          <span className="hidden rounded bg-sim/40 px-1.5 py-[1px] text-[10.5px] font-semibold uppercase tracking-wider text-[#D9D3F7] sm:inline">Demo</span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-[12px]">
              <span className="hidden truncate text-nav-muted md:inline">{demo.title}</span>
              <span className="mono shrink-0 text-nav-muted">{Math.min(doneCount + 1, demo.steps.length)}/{demo.steps.length}</span>
              {paused && <span className="rounded bg-warn px-1 text-[10.5px] font-semibold text-white">Paused</span>}
            </div>
            <div className="truncate text-[13px] font-medium text-white">{cur?.title}{cur?.auto && <span className="ml-2 text-[11.5px] font-normal text-accent-300">running…</span>}</div>
            <div className="mt-1 flex gap-[2px]" aria-hidden>
              {demo.steps.map((s, i) => <span key={s.key} className={clsx("h-[3px] flex-1 rounded-full transition-colors duration-300", s.done ? "bg-accent-300" : i === demo.current ? "bg-white/50" : "bg-white/10")} />)}
            </div>
          </div>
          {cur && (
            <button className="btn h-8 bg-accent-300 px-3 font-semibold text-nav hover:bg-white" onClick={() => next.mutate()} disabled={next.isPending || paused || !!cur.auto} title="Shift+N">
              <SkipForward className="h-4 w-4" aria-hidden /><span className="hidden sm:inline">{cur.view ? "Mark reviewed" : "Next step"}</span><span className="sr-only sm:hidden">{cur.view ? "Mark reviewed" : "Next step"}</span>
            </button>
          )}
          <button className={dockBtn} onClick={() => pause.mutate()} aria-label={paused ? "Resume demo" : "Pause demo"}>{paused ? <Play className="h-4 w-4" aria-hidden /> : <Pause className="h-4 w-4" aria-hidden />}</button>
          <button className={dockBtn} onClick={() => setExpanded((v) => !v)} aria-expanded={expanded} aria-label="Show demo steps and instructions">
            <ChevronUp className={clsx("h-4 w-4 transition-transform", expanded && "rotate-180")} aria-hidden />
          </button>
          <button className={dockBtn} onClick={() => exit.mutate()} aria-label="Exit demo"><LogOut className="h-4 w-4" aria-hidden /></button>
        </div>
      </div>
    </motion.div>
  );
}
