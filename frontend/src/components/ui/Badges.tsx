import clsx from "clsx";
import { Beaker, CircleAlert, CircleCheck, CircleDashed, CircleHelp, CircleMinus, CircleX, Cpu, FileInput, Server, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import type { SourceType } from "@/api/types";

export function Pill({ className, children, title }: { className?: string; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={clsx("inline-flex max-w-full items-center gap-1 whitespace-nowrap rounded-full border px-2 py-[1px] text-[11px] font-semibold leading-[18px]", className)}>
      {children}
    </span>
  );
}

const SRC: Record<SourceType, { label: string; cls: string; icon: typeof Beaker; tip: string }> = {
  SIMULATED: { label: "SIMULATED", cls: "border-sim/25 bg-sim-50 text-sim", icon: Beaker, tip: "Produced by the deterministic simulator. Not collected from hardware." },
  LOCAL_LAB: { label: "LOCAL LAB", cls: "border-lab/25 bg-lab-50 text-lab", icon: Server, tip: "Collected from real lab equipment or a lab-owned process on this machine." },
  IMPORTED_SAMPLE: { label: "IMPORTED SAMPLE", cls: "border-imp/25 bg-imp-50 text-imp", icon: FileInput, tip: "Imported from a bundled or uploaded sample." },
};

export function SourceBadge({ source, compact }: { source: SourceType | string | null | undefined; compact?: boolean }) {
  const s = SRC[(source as SourceType) ?? "SIMULATED"] ?? SRC.SIMULATED;
  const Icon = s.icon;
  return (
    <Pill className={s.cls} title={s.tip}>
      <Icon className="h-3 w-3" aria-hidden />
      {compact ? s.label.split(" ")[0] : s.label}
    </Pill>
  );
}

export function ModeledBadge() {
  return <Pill className="border-line bg-white text-ink-2" title="Synthetic documentation model, not discovered from hardware"><Cpu className="h-3 w-3" aria-hidden />Modeled lab topology</Pill>;
}

const SEV = { critical: "border-crit/30 bg-crit-50 text-crit", major: "border-warn/30 bg-warn-50 text-warn", minor: "border-line-strong bg-canvas text-ink-2" } as const;
export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <Pill className={SEV[severity as keyof typeof SEV] ?? SEV.minor}>
      {severity === "critical" ? <CircleAlert className="h-3 w-3" aria-hidden /> : severity === "major" ? <TriangleAlert className="h-3 w-3" aria-hidden /> : <CircleMinus className="h-3 w-3" aria-hidden />}
      {severity.charAt(0).toUpperCase() + severity.slice(1)}
    </Pill>
  );
}

const STATUS: Record<string, string> = {
  detected: "border-crit/30 bg-crit-50 text-crit",
  acknowledged: "border-warn/30 bg-warn-50 text-warn",
  investigating: "border-accent/30 bg-accent-50 text-accent-700",
  repair_applied: "border-accent/30 bg-accent-50 text-accent-700",
  verification: "border-accent/30 bg-accent-50 text-accent-700",
  resolved: "border-ok/30 bg-ok-50 text-ok",
};
export function StatusBadge({ status }: { status: string }) {
  return <Pill className={STATUS[status] ?? "border-line bg-canvas text-ink-2"}>{status === "resolved" && <CircleCheck className="h-3 w-3" aria-hidden />}{status.replace(/_/g, " ")}</Pill>;
}

const RESULT: Record<string, { cls: string; icon: typeof CircleCheck }> = {
  PASS: { cls: "border-ok/30 bg-ok-50 text-ok", icon: CircleCheck },
  FAIL: { cls: "border-crit/30 bg-crit-50 text-crit", icon: CircleX },
  MANUAL_REVIEW: { cls: "border-warn/30 bg-warn-50 text-warn", icon: CircleHelp },
  UNSUPPORTED: { cls: "border-warn/25 bg-white text-warn", icon: CircleDashed },
  SKIPPED: { cls: "border-line-strong bg-canvas text-ink-2", icon: CircleMinus },
  ERROR: { cls: "border-crit/30 bg-white text-crit", icon: TriangleAlert },
};
export function ResultBadge({ result, size = "sm" }: { result: string | null | undefined; size?: "sm" | "lg" }) {
  if (!result) return <Pill className="border-line bg-canvas text-ink-2"><CircleDashed className="h-3 w-3 animate-spin [animation-duration:3s]" aria-hidden />Pending</Pill>;
  const r = RESULT[result] ?? RESULT.SKIPPED;
  const Icon = r.icon;
  return (
    <Pill className={clsx(r.cls, size === "lg" && "px-3 py-1 text-[13px]")}>
      <Icon className={size === "lg" ? "h-4 w-4" : "h-3 w-3"} aria-hidden />
      {result.replace(/_/g, " ")}
    </Pill>
  );
}

const HEALTH: Record<string, { dot: string; label: string }> = {
  healthy: { dot: "bg-ok", label: "Healthy" },
  degraded: { dot: "bg-warn", label: "Degraded" },
  critical: { dot: "bg-crit animate-pulseRing", label: "Critical" },
  unknown: { dot: "bg-ink-3/50", label: "Unknown" },
  offline: { dot: "bg-ink-3", label: "Offline" },
};
export function HealthDot({ health, withLabel = true }: { health: string; withLabel?: boolean }) {
  const h = HEALTH[health] ?? HEALTH.unknown;
  return (
    <span className="inline-flex items-center gap-1.5 text-[12px] text-ink-2">
      <span className={clsx("led", h.dot)} aria-hidden />
      {withLabel ? <span>{h.label}</span> : <span className="sr-only">{h.label}</span>}
    </span>
  );
}

const LIFECYCLE: Record<string, string> = {
  received: "border-line-strong bg-canvas text-ink-2", stored: "border-line-strong bg-canvas text-ink-2",
  installed: "border-accent/30 bg-accent-50 text-accent-700", active: "border-ok/30 bg-ok-50 text-ok",
  quarantined: "border-warn/30 bg-warn-50 text-warn", in_repair: "border-warn/30 bg-warn-50 text-warn",
  pending_return: "border-crit/25 bg-crit-50 text-crit", returned: "border-line-strong bg-white text-ink-2", decommissioned: "border-line-strong bg-white text-ink-3",
};
export function LifecycleBadge({ status }: { status: string }) {
  return <Pill className={LIFECYCLE[status] ?? LIFECYCLE.received}>{status.replace(/_/g, " ")}</Pill>;
}
