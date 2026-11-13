import clsx from "clsx";
import { motion } from "framer-motion";
import { ArrowRightLeft, Cable as CableIcon, Router, Server, SquareStack } from "lucide-react";
import type { TraceHop } from "@/api/types";
import { CopyButton } from "@/components/ui/Primitives";

const ICON = { server: Server, switch: Router, patch_panel: SquareStack } as Record<string, typeof Server>;

export function CableTrace({ trace }: { trace: { hops: TraceHop[]; text: string; complete: boolean; note: string; basis: string } }) {
  return (
    <div>
      <div className="overflow-x-auto pb-2">
        <ol className="flex min-w-max items-center gap-0" aria-label="Cable path">
          {trace.hops.map((h, i) => {
            const delay = i * 0.12;
            if (h.type === "endpoint") {
              const Icon = ICON[h.role ?? "server"] ?? Server;
              return (
                <motion.li key={i} initial={{ opacity: 0, scale: 0.92 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay, duration: 0.2 }}
                  className="flex min-w-[118px] flex-col items-center rounded-xl border border-line bg-white px-3 py-2 text-center shadow-panel">
                  <Icon className="mb-1 h-4 w-4 text-accent" aria-hidden />
                  <span className="mono font-semibold text-ink">{h.device}</span>
                  <span className="mono text-ink-2">{h.interface}</span>
                  <span className="text-[10.5px] text-ink-3">{h.connector}</span>
                </motion.li>
              );
            }
            if (h.type === "pass_through") {
              return (
                <motion.li key={i} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay }} className="flex flex-col items-center px-2 text-[10.5px] text-ink-2">
                  <ArrowRightLeft className="h-3.5 w-3.5 text-ink-3" aria-hidden />
                  <span>pass-through</span>
                </motion.li>
              );
            }
            return (
              <li key={i} className="relative flex w-[150px] flex-col items-center px-1">
                <svg viewBox="0 0 150 20" className="h-5 w-full" aria-hidden>
                  <motion.path d="M2 10 C 40 2, 110 18, 148 10" fill="none" strokeWidth={2.5} strokeLinecap="round"
                    className={clsx(h.status === "connected" ? "stroke-accent" : "stroke-warn", !h.label && "[stroke-dasharray:5_4]")}
                    initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ delay, duration: 0.45, ease: "easeInOut" }} />
                </svg>
                <span className={clsx("mono mt-0.5 flex items-center gap-1 rounded px-1.5", h.label ? "bg-accent-50 text-accent-700" : "bg-warn-50 text-warn")}>
                  <CableIcon className="h-3 w-3" aria-hidden />{h.label ?? "UNLABELED"}
                </span>
                <span className="text-[10.5px] text-ink-3">{h.cable_type}{h.length_m ? ` · ${h.length_m} m` : ""}{h.intended_speed_mbps ? ` · ${h.intended_speed_mbps / 1000}G` : ""}</span>
              </li>
            );
          })}
        </ol>
      </div>
      <div className="mt-2 rounded-lg border border-line-soft bg-canvas px-3 py-2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="eyebrow mb-0.5">Text path ({trace.basis})</div>
            <p className="mono break-words text-ink">{trace.text}</p>
          </div>
          <CopyButton text={trace.text} label="Copy path" />
        </div>
        <p className={clsx("mt-1 text-[12px]", trace.complete ? "text-ok" : "text-warn")}>{trace.complete ? "Path terminates on an active device." : trace.note}</p>
      </div>
    </div>
  );
}
