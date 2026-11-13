import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowRight, Boxes, CheckCircle2, ClipboardCheck, Clapperboard, PackageMinus, PlayCircle, Server, Siren, Undo2, Wrench,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useIncidents, useIntakes, useOverview, useRacks } from "@/api/hooks";
import type { AuditEvent, Rack } from "@/api/types";
import { ProductTourHero, ProductTourPlayer, useProductTour } from "@/components/ProductTour";
import { DeviceDrawer } from "@/components/rack/DevicePanel";
import { populatedRange, RackElevation, RackTable } from "@/components/rack/RackElevation";
import { Pill, SeverityBadge } from "@/components/ui/Badges";
import { Empty, ErrorState, LoadingBlock, Modal, Panel, Stat } from "@/components/ui/Primitives";
import { age, fmtDateTime, relative } from "@/lib/format";

// ---------------------------------------------------------------- needs attention

type Attention = { key: string; kind: "Incident" | "Acceptance" | "Stock"; subject: string; issue: string; rank: number; severity: string; age: string; to: string };

function useAttention(): { items: Attention[]; loading: boolean } {
  const incs = useIncidents("open_only=true&limit=50");
  const intakes = useIntakes();
  const ov = useOverview();
  const items = useMemo(() => {
    const out: Attention[] = [];
    for (const i of incs.data?.items ?? []) {
      out.push({ key: `i${i.id}`, kind: "Incident", subject: i.device?.display_id ?? i.display_id, issue: i.title, severity: i.severity,
        rank: i.severity === "critical" ? 0 : i.severity === "major" ? 2 : 4, age: age(i.detected_at), to: `/incidents/${i.id}` });
    }
    for (const x of intakes.data ?? []) {
      if (x.status !== "failed" && x.status !== "manual_review") continue;
      const last = x.runs.at(-1);
      out.push({ key: `a${x.id}`, kind: "Acceptance", subject: x.hostname, issue: x.status === "failed" ? `Run #${last?.run_number ?? "?"} failed` : "Evidence needs review",
        severity: x.status === "failed" ? "major" : "minor", rank: x.status === "failed" ? 1 : 3, age: age(last?.completed_at),
        to: `/acceptance/${x.id}${last ? `?run=${last.id}` : ""}` });
    }
    for (const s of ov.data?.low_stock.items ?? []) {
      out.push({ key: `s${s.id}`, kind: "Stock", subject: s.part_number, issue: `${s.available} available, reorder at ${s.reorder_threshold}`, severity: "minor", rank: 5, age: "", to: "/spares?low=1" });
    }
    return out.sort((a, b) => a.rank - b.rank);
  }, [incs.data, intakes.data, ov.data]);
  return { items, loading: incs.isLoading || intakes.isLoading || ov.isLoading };
}

const KIND_ICON = { Incident: Siren, Acceptance: ClipboardCheck, Stock: PackageMinus };

function NeedsAttention() {
  const { items, loading } = useAttention();
  const shown = items.slice(0, 5);
  return (
    <Panel title="Needs attention" sub={items.length ? `${items.length} open item${items.length === 1 ? "" : "s"}` : undefined} bodyClass=""
      actions={items.length > 5 && <Link to="/incidents?open=1" className="btn-ghost btn-sm">View all <ArrowRight className="h-3.5 w-3.5" aria-hidden /></Link>}>
      {loading ? <LoadingBlock rows={4} /> : shown.length === 0 ? (
        <Empty title="Nothing needs attention" icon={<CheckCircle2 className="h-5 w-5 text-ok" />}>No open incidents, failed acceptance runs or low stock.</Empty>
      ) : (
        <ul className="divide-y divide-line-soft">
          {shown.map((a, i) => {
            const Icon = KIND_ICON[a.kind];
            return (
              <motion.li key={a.key} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.04, duration: 0.2 }}>
                <Link to={a.to} className="group flex items-center gap-3 px-4 py-3 transition-colors hover:bg-canvas">
                  <span className={clsx("grid h-8 w-8 shrink-0 place-items-center rounded-lg",
                    a.severity === "critical" ? "bg-crit-50 text-crit" : a.severity === "major" ? "bg-warn-50 text-warn" : "bg-canvas text-ink-2")}>
                    <Icon className="h-4 w-4" aria-hidden />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="mono truncate font-medium text-ink">{a.subject}</span>
                      <span className="text-[11px] text-ink-3">{a.kind}</span>
                    </div>
                    <div className="truncate text-[12.5px] text-ink-2">{a.issue}</div>
                  </div>
                  {a.kind === "Stock" ? <Pill className="border-warn/30 bg-warn-50 text-warn">Low stock</Pill> : <SeverityBadge severity={a.severity} />}
                  <span className="mono hidden w-10 shrink-0 text-right text-[11.5px] text-ink-3 sm:block" title="Age">{a.age}</span>
                  <ArrowRight className="h-4 w-4 shrink-0 text-ink-3 opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
                </Link>
              </motion.li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------- infrastructure

function InfrastructurePanel() {
  const racks = useRacks();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const [rackId, setRackId] = useState<string | null>(null);
  const [text, setText] = useState(false);
  const rack: Rack | undefined = racks.data?.find((r) => r.display_id === rackId) ?? racks.data?.[0];
  const selected = params.get("device");
  const range = rack ? populatedRange(rack) : null;
  const devices = rack?.devices.filter((d) => d.role !== "pdu") ?? [];
  const unhealthy = devices.filter((d) => d.health !== "healthy");
  const findings = devices.reduce((n, d) => n + d.power_findings.length, 0);

  return (
    <Panel title="Infrastructure" bodyClass="p-4"
      actions={<>
        {racks.data && racks.data.length > 1 && (
          <div className="flex rounded-lg border border-line p-0.5" role="group" aria-label="Rack">
            {racks.data.map((r) => (
              <button key={r.id} onClick={() => setRackId(r.display_id)} aria-pressed={rack?.id === r.id}
                className={clsx("mono rounded-md px-2 py-0.5 text-[11.5px] font-medium transition-colors", rack?.id === r.id ? "bg-nav text-white" : "text-ink-2 hover:text-ink")}>{r.display_id}</button>
            ))}
          </div>
        )}
        <button className="btn-ghost btn-sm" onClick={() => setText((t) => !t)} aria-pressed={text}>{text ? "Visual" : "Text"}</button>
      </>}>
      {racks.isLoading ? <LoadingBlock rows={8} /> : racks.error ? <ErrorState error={racks.error} /> : rack && range && (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-[minmax(0,1fr)_180px]">
          <div className="min-w-0">
            {text ? <div className="overflow-x-auto"><RackTable rack={rack} /></div> : (
              <RackElevation rack={rack} compact range={range} selected={selected}
                onSelect={(d) => setParams((p) => { p.set("device", d.display_id); return p; })} />
            )}
            <p className="mt-2 text-[11.5px] text-ink-3">
              Showing <span className="mono">U{range[0]}–U{range[1]}</span> of {rack.u_height}U · {rack.free_units}U free in rack · modeled rack
            </p>
          </div>
          <div className="flex flex-col gap-3 text-[13px]">
            <dl className="space-y-2.5">
              <div><dt className="text-[11.5px] text-ink-2">Devices</dt><dd className="text-[18px] font-semibold tabular-nums">{devices.length}</dd></div>
              <div><dt className="text-[11.5px] text-ink-2">Health</dt>
                <dd className={clsx("font-medium", unhealthy.length ? "text-crit" : "text-ink")}>
                  {unhealthy.length ? unhealthy.map((d) => `${d.display_id} ${d.health}`).join(", ") : "All healthy"}
                </dd></div>
              <div><dt className="text-[11.5px] text-ink-2">Planned installs</dt><dd>{rack.planned.length ? rack.planned.map((p) => p.hostname).join(", ") : "None"}</dd></div>
              <div><dt className="text-[11.5px] text-ink-2">Documentation findings</dt>
                <dd className={findings ? "text-warn" : "text-ink"}>{findings ? `${findings} power finding${findings > 1 ? "s" : ""}` : "None"}</dd></div>
            </dl>
            <div className="mt-auto flex flex-col gap-1.5">
              <button className="btn-secondary btn-sm justify-start" onClick={() => nav(`/infrastructure?rack=${rack.display_id}`)}>View full rack</button>
              <Link to="/infrastructure?tab=cables" className="btn-ghost btn-sm justify-start">Cabling and power</Link>
            </div>
          </div>
        </div>
      )}
      <DeviceDrawer id={selected} onClose={() => setParams((p) => { p.delete("device"); return p; })} />
    </Panel>
  );
}

// ---------------------------------------------------------------- recent activity

const MEANINGFUL: Record<string, { label: (a: AuditEvent) => string; icon: typeof Siren }> = {
  "incident.detected": { label: () => "Incident detected", icon: Siren },
  "incident.resolved": { label: () => "Incident resolved", icon: CheckCircle2 },
  "acceptance.run_completed": { label: (a) => `Acceptance ${String(a.after?.disposition ?? "").replace("_", " ").toLowerCase()}`, icon: ClipboardCheck },
  "reservation.create": { label: () => "Spare reserved", icon: Boxes },
  "reservation.consume": { label: () => "Spare consumed", icon: Wrench },
  "return.create": { label: () => "Return opened", icon: Undo2 },
  "asset.transition": { label: (a) => `Asset ${String(a.after?.status ?? "updated").replace("_", " ")}`, icon: Server },
  "intake.handoff": { label: () => "Handed off to provisioning", icon: ClipboardCheck },
};

function subjectOf(a: AuditEvent) {
  const dev = a.related?.find((r) => r.type === "device");
  return dev?.display ?? a.entity_display;
}

function RecentActivity() {
  const ov = useOverview();
  const rows = (ov.data?.recent_events as AuditEvent[] | undefined ?? []).filter((a) => MEANINGFUL[a.action]).slice(0, 5);
  return (
    <Panel title="Recent activity" bodyClass="" actions={<Link to="/settings#audit" className="btn-ghost btn-sm">Full history <ArrowRight className="h-3.5 w-3.5" aria-hidden /></Link>}>
      {!ov.data ? <LoadingBlock rows={3} /> : rows.length === 0 ? <Empty title="No recent activity">Activity appears here as incidents, acceptance runs and inventory change.</Empty> : (
        <ul className="divide-y divide-line-soft">
          {rows.map((a) => {
            const m = MEANINGFUL[a.action];
            return (
              <li key={a.id} className="flex items-center gap-3 px-4 py-2.5 text-[13px]">
                <m.icon className="h-4 w-4 shrink-0 text-ink-3" aria-hidden />
                <div className="flex min-w-0 flex-1 flex-col sm:flex-row sm:items-center sm:gap-3">
                  <span className="truncate font-medium text-ink sm:w-52 sm:shrink-0">{m.label(a)}</span>
                  <span className="mono min-w-0 truncate text-[12px] text-ink-2 sm:text-[13px]">{subjectOf(a)}</span>
                </div>
                {a.origin === "simulation" && <span className="hidden text-[11px] text-sim md:inline">simulated</span>}
                <time className="mono shrink-0 text-[11.5px] text-ink-3" dateTime={a.occurred_at} title={fmtDateTime(a.occurred_at)}>{relative(a.occurred_at)}</time>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------- page

export function Overview() {
  const ov = useOverview();
  const intakes = useIntakes();
  const o = ov.data;
  const accAttention = (intakes.data ?? []).filter((x) => x.status === "failed" || x.status === "manual_review").length;
  const unhealthy = o ? o.devices.total - o.devices.healthy : 0;
  const tour = useProductTour();
  return (
    <div className="space-y-5">
      <AnimatePresence initial={false}>
        {!tour.dismissed && <ProductTourHero key="tour" onPlay={() => tour.setOpen(true)} onDismiss={tour.dismiss} playerOpen={tour.open} />}
      </AnimatePresence>
      <ProductTourPlayer open={tour.open} onOpenChange={tour.setOpen} />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-semibold leading-tight text-ink">Operations Overview</h1>
          <p className="mt-0.5 text-[13px] text-ink-2">Infrastructure health and priority work.</p>
        </div>
        <div className="flex items-center gap-2">
          {tour.dismissed && (
            <button className="btn-ghost" onClick={() => tour.setOpen(true)}><Clapperboard className="h-4 w-4" aria-hidden />Watch tour</button>
          )}
          <Link to="/demo" className="btn-secondary"><PlayCircle className="h-4 w-4" aria-hidden />Run demo</Link>
        </div>
      </div>


      {ov.error && <ErrorState error={ov.error} retry={() => ov.refetch()} />}
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Stat label="Healthy devices" to="/assets?type=server,switch" tone={unhealthy ? "warn" : "default"}
          value={o ? <>{o.devices.healthy}<span className="text-[15px] font-normal text-ink-3"> / {o.devices.total}</span></> : "–"}
          sub={o ? (unhealthy ? `${unhealthy} not healthy` : "All reporting healthy") : " "} />
        <Stat label="Open incidents" to="/incidents?open=1" tone={o?.open_incidents.critical ? "crit" : o?.open_incidents.total ? "warn" : "default"}
          value={o?.open_incidents.total ?? "–"} sub={o ? (o.open_incidents.total ? `${o.open_incidents.critical} critical` : "None open") : " "} />
        <Stat label="Acceptance attention" to="/acceptance?attention=1" tone={accAttention ? "warn" : "default"}
          value={intakes.data ? accAttention : "–"} sub={o ? `${o.acceptance.awaiting} awaiting first run` : " "} />
        <Stat label="Low-stock parts" to="/spares?low=1" tone={o?.low_stock.total ? "warn" : "default"}
          value={o?.low_stock.total ?? "–"} sub={o ? (o.low_stock.total ? "Below reorder threshold" : "All above threshold") : " "} />
      </div>

      <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <InfrastructurePanel />
        <NeedsAttention />
      </div>
      <RecentActivity />
    </div>
  );
}

// ---------------------------------------------------------------- shared: drill picker (used by Incidents)

export function DrillPicker({ open, onOpenChange, scenarios, onStart, pending }: { open: boolean; onOpenChange: (o: boolean) => void; scenarios: any[]; onStart: (k: string) => void; pending: boolean }) {
  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Run a simulated drill" description="Deterministic: the same baseline, fault and evidence every time. Nothing on this machine is touched." wide>
      <ul className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        {scenarios.map((s) => (
          <li key={s.key} className="flex flex-col rounded-xl border border-line p-3">
            <div className="flex items-center gap-2"><SeverityBadge severity={s.severity} /><span className="mono text-[11.5px] text-ink-2">{s.device}</span></div>
            <div className="mt-1.5 text-[13.5px] font-semibold text-ink">{s.title}</div>
            <p className="mt-1 text-[12px] text-ink-2">{s.symptom}</p>
            {!s.onset_known && <p className="mt-1 text-[11.5px] text-warn">Onset unknown: detection latency will be unavailable.</p>}
            <div className="mt-auto pt-3">
              {s.active_run ? (
                <Link to={s.active_run.incident_id ? `/incidents/${s.active_run.incident_id}` : "/"} className="btn-secondary btn-sm" onClick={() => onOpenChange(false)}>View active drill</Link>
              ) : (
                <button className="btn-primary btn-sm" disabled={pending} onClick={() => onStart(s.key)}>Start drill</button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </Modal>
  );
}
