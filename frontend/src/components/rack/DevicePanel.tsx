import * as Dialog from "@radix-ui/react-dialog";
import * as Tabs from "@radix-ui/react-tabs";
import clsx from "clsx";
import { motion } from "framer-motion";
import { ExternalLink, Route, ShieldAlert, X, Zap } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useDevice } from "@/api/hooks";
import type { DeviceDetail, TraceHop } from "@/api/types";
import { HealthDot, LifecycleBadge, ModeledBadge, Pill, ResultBadge, SeverityBadge, SourceBadge, StatusBadge } from "@/components/ui/Badges";
import { Empty, ErrorState, KV, LoadingBlock } from "@/components/ui/Primitives";
import { fmtDateTime, human, relative } from "@/lib/format";
import { CableTrace } from "./CableTrace";
import { QrLabel } from "./QrLabel";

export function AuditList({ items }: { items: DeviceDetail["audit"] }) {
  if (!items.length) return <Empty title="No audit events yet" />;
  return (
    <ol className="relative space-y-0 border-l border-line pl-4">
      {items.map((a, i) => (
        <motion.li key={a.id} initial={{ opacity: 0, x: -4 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i * 0.02, 0.3) }} className="relative pb-3">
          <span className={clsx("absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white", a.origin === "simulation" ? "bg-sim" : a.origin === "seed" ? "bg-ink-3" : "bg-accent")} aria-hidden />
          <div className="flex flex-wrap items-baseline gap-x-2 text-[12.5px]">
            <span className="mono text-ink-3">{fmtDateTime(a.occurred_at)}</span>
            <span className="mono font-medium text-ink">{a.action}</span>
            <span className="text-ink-2">by {a.actor}</span>
            {a.origin === "simulation" && <Pill className="border-sim/25 bg-sim-50 text-sim">simulation</Pill>}
          </div>
          <div className="text-[13px] text-ink">{a.summary}</div>
          {(a.before || a.after) && (
            <div className="mono mt-0.5 break-words text-[11px] text-ink-2">
              {a.before && <span>before {JSON.stringify(a.before)} </span>}{a.after && <span>→ after {JSON.stringify(a.after)}</span>}
            </div>
          )}
        </motion.li>
      ))}
    </ol>
  );
}

export function DevicePanel({ id, initialTab = "overview" }: { id: string | number; initialTab?: string }) {
  const dq = useDevice(id);
  const [trace, setTrace] = useState<{ hops: TraceHop[]; text: string; complete: boolean; note: string; basis: string } | null>(null);
  const [tracing, setTracing] = useState<number | null>(null);
  if (dq.isLoading) return <LoadingBlock rows={8} label="Loading device" />;
  if (dq.error) return <ErrorState error={dq.error} retry={() => dq.refetch()} />;
  const d = dq.data!;
  const doTrace = async (iid: number) => {
    setTracing(iid);
    try { setTrace(await api(`/interfaces/${iid}/trace`)); } finally { setTracing(null); }
  };
  const tabs = [
    ["overview", "Overview"], ["interfaces", `Interfaces · ${d.interfaces.length}`], ["power", "Power"],
    ["incidents", `Incidents · ${d.incidents.length}`], ["acceptance", "Acceptance"], ["lifecycle", "Lifecycle"], ["audit", "Audit"],
  ];
  return (
    <Tabs.Root defaultValue={initialTab} className="flex min-h-0 flex-col">
      <Tabs.List className="-mx-1 mb-4 flex gap-0.5 overflow-x-auto border-b border-line px-1" aria-label="Device sections">
        {tabs.map(([v, l]) => (
          <Tabs.Trigger key={v} value={v} className="relative whitespace-nowrap px-2.5 pb-2 pt-1 text-[12.5px] font-medium text-ink-2 transition-colors hover:text-ink data-[state=active]:text-accent-700 data-[state=active]:after:absolute data-[state=active]:after:inset-x-1 data-[state=active]:after:-bottom-px data-[state=active]:after:h-[2px] data-[state=active]:after:rounded-full data-[state=active]:after:bg-accent">
            {l}
          </Tabs.Trigger>
        ))}
      </Tabs.List>

      <Tabs.Content value="overview" className="space-y-4 outline-none">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <dl className="divide-y divide-line-soft rounded-xl border border-line px-3">
            <KV k="Role" v={human(d.role)} />
            <KV k="Model" v={d.model} />
            <KV k="Manufacturer" v={d.manufacturer} />
            <KV k="Position" v={d.rack ? `${d.rack} · U${d.position_u}${d.u_height > 1 ? `–U${(d.position_u ?? 0) + d.u_height - 1}` : ""}` : "Not racked"} mono />
            <KV k="Management address" v={d.mgmt_address || "—"} mono />
            <KV k="Asset tag" v={d.asset ?? "—"} mono />
            <KV k="Serial" v={d.serial ?? "—"} mono />
          </dl>
          <div className="space-y-3">
            <div className="rounded-xl border border-line p-3">
              <div className="eyebrow mb-1.5">Health</div>
              <div className="flex flex-wrap items-center gap-2"><HealthDot health={d.health} /><SourceBadge source={d.health_source} /></div>
              <div className="mt-1 text-[12px] text-ink-2">Last reported {relative(d.health_updated_at)} · <span className="mono">{fmtDateTime(d.health_updated_at)}</span></div>
            </div>
            {d.power.findings.length > 0 && (
              <div className="rounded-xl border border-warn/30 bg-warn-50/60 p-3">
                <div className="eyebrow mb-1 flex items-center gap-1 text-warn"><ShieldAlert className="h-3 w-3" aria-hidden />Documentation findings</div>
                <ul className="space-y-1 text-[12.5px] text-ink">{d.power.findings.map((f) => <li key={f.code + f.message}>• {f.message}</li>)}</ul>
              </div>
            )}
            {d.notes && <p className="text-[12.5px] text-ink-2">{d.notes}</p>}
            <ModeledBadge />
          </div>
        </div>
        {d.asset && (
          <div className="flex flex-wrap items-center gap-3">
            <QrLabel title={d.display_id} subtitle={`${d.asset} · ${d.serial}`} path={`/assets/${d.asset_id}`} />
            <button className="btn-secondary btn-sm no-print" onClick={() => window.print()}>Print label</button>
          </div>
        )}
      </Tabs.Content>

      <Tabs.Content value="interfaces" className="space-y-4 outline-none">
        <div className="overflow-x-auto rounded-xl border border-line">
          <table className="table">
            <thead><tr><th>Interface</th><th>Kind</th><th>Connector</th><th>Capability</th><th>Cable</th><th className="sr-only">Actions</th></tr></thead>
            <tbody>
              {d.interfaces.map((i) => {
                const c = d.cables.find((c) => c.a.interface_id === i.id || c.b.interface_id === i.id);
                const far = c ? (c.a.interface_id === i.id ? c.b : c.a) : null;
                return (
                  <tr key={i.id}>
                    <td className="mono font-medium">{i.name}</td>
                    <td>{human(i.kind)}</td>
                    <td className="mono">{i.connector}</td>
                    <td className="mono">{i.speed_capability_mbps ? `${i.speed_capability_mbps} Mb/s` : "Unknown"}</td>
                    <td>{c ? <span className="mono">{c.label ?? <span className="text-warn">UNLABELED</span>} → {far?.device}:{far?.interface}</span> : <span className="text-ink-3">No modeled cable</span>}</td>
                    <td className="text-right">
                      <button className="btn-ghost btn-sm" onClick={() => doTrace(i.id)} disabled={tracing === i.id} aria-label={`Trace path from ${i.name}`}>
                        <Route className="h-3.5 w-3.5" aria-hidden />Trace
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {trace && <div className="rounded-xl border border-line p-3"><CableTrace trace={trace} /></div>}
      </Tabs.Content>

      <Tabs.Content value="power" className="space-y-3 outline-none">
        <div className="flex flex-wrap items-center gap-2 text-[13px]">
          <span className="text-ink-2">Upstream independence:</span>
          <Pill className={d.power.independence.startsWith("independent") ? "border-ok/30 bg-ok-50 text-ok" : d.power.independence === "not independent" ? "border-crit/30 bg-crit-50 text-crit" : "border-warn/30 bg-warn-50 text-warn"}>{d.power.independence}</Pill>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {d.power.inputs.map((p) => (
            <div key={p.input} className={clsx("rounded-xl border p-3", p.outlet ? "border-line" : "border-dashed border-crit/50 bg-crit-50/40")}>
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 font-semibold text-ink"><Zap className="h-3.5 w-3.5 text-warn" aria-hidden />{p.input}</span>
                <span className="mono text-ink-3">{p.connector}</span>
              </div>
              <dl className="mt-1">
                <KV k="Outlet" v={p.outlet ?? "Not connected"} mono />
                <KV k="Feed" v={p.feed ?? "—"} mono />
                <KV k="Upstream" v={p.upstream ?? (p.feed ? "Unknown" : "—")} />
                <KV k="Load (estimate)" v={p.estimated_load_w !== null ? `~${p.estimated_load_w} W of ${p.rated_w} W` : "Not modeled"} />
                <KV k="Component" v={p.component_asset ?? "Not tracked"} mono />
              </dl>
            </div>
          ))}
        </div>
        <p className="text-[11.5px] text-ink-2">{d.power.disclaimer}</p>
      </Tabs.Content>

      <Tabs.Content value="incidents" className="outline-none">
        {d.incidents.length === 0 ? <Empty title="No incidents recorded for this device" /> : (
          <ul className="space-y-2">
            {d.incidents.map((i) => (
              <li key={i.id}>
                <Link to={`/incidents/${i.id}`} className="flex flex-wrap items-center gap-2 rounded-xl border border-line p-3 transition-colors hover:border-accent/40 hover:bg-accent-50/30">
                  <span className="mono font-semibold">{i.display_id}</span><SeverityBadge severity={i.severity} /><StatusBadge status={i.status} /><SourceBadge source={i.source_type} compact />
                  <span className="min-w-0 flex-1 truncate text-[13px]">{i.title}</span>
                  <span className="mono text-ink-3">{fmtDateTime(i.detected_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Tabs.Content>

      <Tabs.Content value="acceptance" className="outline-none">
        {d.acceptance.length === 0 ? <Empty title="No acceptance history">Seeded racked servers predate the intake workflow. New servers get an intake record.</Empty> : (
          d.acceptance.map((x) => (
            <div key={x.id} className="space-y-2">
              {x.runs.map((r) => (
                <Link key={r.id} to={`/acceptance/${x.id}?run=${r.id}`} className="flex items-center gap-2 rounded-lg border border-line p-2.5 hover:bg-canvas">
                  <span className="mono">{r.display_id}</span><ResultBadge result={r.disposition} /><SourceBadge source={r.source_type} compact /><span className="mono ml-auto text-ink-3">{fmtDateTime(r.completed_at)}</span>
                </Link>
              ))}
            </div>
          ))
        )}
      </Tabs.Content>

      <Tabs.Content value="lifecycle" className="space-y-3 outline-none">
        {d.asset_detail && (
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-line p-3">
            <span className="mono font-semibold">{d.asset_detail.display_id}</span><LifecycleBadge status={d.asset_detail.status} />
            <span className="text-[12.5px] text-ink-2">Warranty: {human(d.asset_detail.warranty_status)}</span>
            <Link to={`/assets/${d.asset_detail.id}`} className="btn-ghost btn-sm ml-auto">Open asset <ExternalLink className="h-3 w-3" aria-hidden /></Link>
          </div>
        )}
        <div className="eyebrow">Tracked components</div>
        {d.components.length === 0 ? <p className="text-[13px] text-ink-2">No components tracked.</p> : (
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {d.components.map((c) => (
              <li key={c.id}><Link to={`/assets/${c.id}`} className="flex items-center gap-2 rounded-lg border border-line p-2.5 hover:bg-canvas">
                <span className="mono font-medium">{c.display_id}</span><LifecycleBadge status={c.status} /><span className="mono truncate text-[11px] text-ink-3">{c.serial_number}</span>
              </Link></li>
            ))}
          </ul>
        )}
      </Tabs.Content>

      <Tabs.Content value="audit" className="outline-none"><AuditList items={d.audit} /></Tabs.Content>
    </Tabs.Root>
  );
}

export function DeviceDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const dq = useDevice(id);
  return (
    <Dialog.Root open={!!id} onOpenChange={(o) => !o && onClose()} modal={false}>
      <Dialog.Portal>
        <Dialog.Content className="fixed inset-y-0 right-0 z-[56] flex w-full max-w-[720px] flex-col border-l border-line bg-white shadow-[-24px_0_60px_-20px_rgba(16,24,39,0.35)] outline-none data-[state=open]:animate-[slideIn_220ms_cubic-bezier(.2,.8,.2,1)]"
          aria-describedby={undefined}>
          <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
            <div className="min-w-0">
              <div className="eyebrow">Device</div>
              <Dialog.Title className="mono truncate text-[17px] font-semibold text-ink">{id}</Dialog.Title>
              {dq.data && <div className="mt-1 flex flex-wrap items-center gap-2"><HealthDot health={dq.data.health} />
                {dq.data.open_incidents.map((i) => <Link key={i.id} to={`/incidents/${i.id}`}><SeverityBadge severity={i.severity} /></Link>)}</div>}
            </div>
            <div className="flex items-center gap-1">
              {dq.data?.asset_id && <Link to={`/assets/${dq.data.asset_id}`} className="btn-secondary btn-sm">Full page</Link>}
              <Dialog.Close className="rounded-md p-1.5 text-ink-3 hover:bg-canvas hover:text-ink" aria-label="Close device panel"><X className="h-4 w-4" /></Dialog.Close>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-5">{id && <DevicePanel id={id} />}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
