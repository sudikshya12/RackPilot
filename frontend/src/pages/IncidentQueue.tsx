import clsx from "clsx";
import { motion } from "framer-motion";
import { ArrowRight, FlaskConical, Info, SlidersHorizontal, Timer } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { post } from "@/api/client";
import { useAction, useIncidents, useMetrics, useScenarios } from "@/api/hooks";
import type { SourceType } from "@/api/types";
import { SeverityBadge, SourceBadge, StatusBadge } from "@/components/ui/Badges";
import { Empty, ErrorState, LoadingBlock, PageHeader, Panel } from "@/components/ui/Primitives";
import { elapsedSince, fmtDateTime, fmtDuration } from "@/lib/format";
import { DrillPicker } from "./Operations";

const FILTERS = {
  severity: ["critical", "major", "minor"],
  status: ["detected", "acknowledged", "investigating", "repair_applied", "verification", "resolved"],
  source: ["SIMULATED", "LOCAL_LAB", "IMPORTED_SAMPLE"],
};

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} aria-pressed={active}
      className={clsx("h-7 rounded-full border px-2.5 text-[12px] font-medium capitalize transition-colors duration-150",
        active ? "border-accent bg-accent text-white" : "border-line bg-white text-ink-2 hover:border-line-strong hover:text-ink")}>{children}</button>
  );
}

export function IncidentQueue() {
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const scenarios = useScenarios();
  const [drillOpen, setDrillOpen] = useState(false);
  const startDrill = useAction((key: string) => post(`/scenarios/${key}/start`), { success: "Drill started", onSuccess: () => setDrillOpen(false) });

  const get = (k: string) => (params.get(k) ?? "").split(",").filter(Boolean);
  const toggle = (k: string, v: string) => setParams((p) => {
    const cur = new Set(get(k));
    cur.has(v) ? cur.delete(v) : cur.add(v);
    cur.size ? p.set(k, [...cur].join(",")) : p.delete(k);
    return p;
  });
  const qs = useMemo(() => {
    const p = new URLSearchParams();
    for (const k of ["severity", "status", "source", "scenario", "device"]) if (params.get(k)) p.set(k, params.get(k)!);
    if (params.get("open")) p.set("open_only", "true");
    p.set("limit", "200");
    return p.toString();
  }, [params]);
  const q = useIncidents(qs);
  const activeCount = ["severity", "status", "source", "scenario", "device", "open"].filter((k) => params.get(k)).length;
  const active = activeCount > 0;
  const [showFilters, setShowFilters] = useState(false);

  return (
    <div className="space-y-5">
      <PageHeader title="Incidents"
        actions={<button className="btn-primary" onClick={() => setDrillOpen(true)}><FlaskConical className="h-4 w-4" aria-hidden />Run a drill</button>}>
        Critical unresolved first, then oldest unacknowledged.
      </PageHeader>

      <div className="flex flex-wrap items-center gap-2">
        <button className="btn-secondary btn-sm" onClick={() => setShowFilters((v) => !v)} aria-expanded={showFilters || undefined} aria-controls="incident-filters">
          <SlidersHorizontal className="h-3.5 w-3.5" aria-hidden />Filters{active ? ` · ${activeCount}` : ""}
        </button>
        <Chip active={!!params.get("open")} onClick={() => setParams((p) => { p.get("open") ? p.delete("open") : p.set("open", "1"); return p; })}>Unresolved only</Chip>
        {active && <button className="btn-ghost btn-sm" onClick={() => setParams({})}>Clear</button>}
      </div>
      {showFilters && <div id="incident-filters" className="panel space-y-2.5 p-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="eyebrow mr-1 w-16">Severity</span>
          {FILTERS.severity.map((s) => <Chip key={s} active={get("severity").includes(s)} onClick={() => toggle("severity", s)}>{s}</Chip>)}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="eyebrow mr-1 w-16">Status</span>
          {FILTERS.status.map((s) => <Chip key={s} active={get("status").includes(s)} onClick={() => toggle("status", s)}>{s.replace("_", " ")}</Chip>)}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="eyebrow mr-1 w-16">Source</span>
          {FILTERS.source.map((s) => <Chip key={s} active={get("source").includes(s)} onClick={() => toggle("source", s)}>{s.replace("_", " ").toLowerCase()}</Chip>)}
          <label className="eyebrow ml-3 mr-1" htmlFor="f-scn">Scenario</label>
          <select id="f-scn" className="input h-7 w-auto py-0 text-[12px]" value={params.get("scenario") ?? ""}
            onChange={(e) => setParams((p) => { e.target.value ? p.set("scenario", e.target.value) : p.delete("scenario"); return p; })}>
            <option value="">Any</option>
            {(scenarios.data ?? []).map((s) => <option key={s.key} value={s.key}>{s.key}</option>)}
          </select>
          <label className="eyebrow ml-3 mr-1" htmlFor="f-dev">Device</label>
          <input id="f-dev" className="input h-7 w-36 py-0 text-[12px]" placeholder="lab-srv-02" defaultValue={params.get("device") ?? ""}
            onKeyDown={(e) => { if (e.key === "Enter") { const v = (e.target as HTMLInputElement).value.trim(); setParams((p) => { v ? p.set("device", v) : p.delete("device"); return p; }); } }} />
        </div>
      </div>}

      <Panel title={`Incidents${q.data ? ` · ${q.data.total}` : ""}`} bodyClass="">
        {q.isLoading ? <LoadingBlock rows={6} /> : q.error ? <div className="p-4"><ErrorState error={q.error} retry={() => q.refetch()} /></div> : !q.data?.items.length ? (
          <Empty title={active ? "No incidents match these filters" : "No incidents yet"} action={<button className="btn-primary btn-sm" onClick={() => setDrillOpen(true)}>Run a drill</button>}>
            Incidents appear here when a detection rule fires: simulated drills, the opt-in live lab, or imported alerts.
          </Empty>
        ) : (
          <>
            <div className="hidden overflow-x-auto md:block">
              <table className="table">
                <thead><tr><th>Severity</th><th>Incident</th><th>Device</th><th>Status</th><th>Source</th><th>Detected</th><th>Elapsed</th><th>Assigned</th><th>Next step</th></tr></thead>
                <tbody>
                  {q.data.items.map((i, idx) => (
                    <motion.tr key={i.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: Math.min(idx * 0.025, 0.25) }}
                      className="cursor-pointer" onClick={() => nav(`/incidents/${i.id}`)}>
                      <td><SeverityBadge severity={i.severity} /></td>
                      <td className="max-w-[280px]"><Link to={`/incidents/${i.id}`} className="mono font-semibold text-ink hover:text-accent-700">{i.display_id}</Link><div className="truncate text-[12.5px] text-ink-2" title={i.symptom}>{i.title}</div></td>
                      <td className="mono">{i.device?.display_id ?? "—"}</td>
                      <td><StatusBadge status={i.status} />{i.reopen_count > 0 && <div className="mt-0.5 text-[10.5px] text-warn">reopened ×{i.reopen_count}</div>}</td>
                      <td><SourceBadge source={i.source_type} compact /></td>
                      <td className="mono whitespace-nowrap text-ink-2">{fmtDateTime(i.detected_at)}</td>
                      <td className="mono whitespace-nowrap">{i.status === "resolved" ? <span className="text-ok">resolved</span> : elapsedSince(i.detected_at)}</td>
                      <td>{i.assigned_operator ?? <span className="text-ink-3">Unassigned</span>}</td>
                      <td className="max-w-[240px] text-[12.5px] text-accent-700">{i.next_step}</td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="divide-y divide-line-soft md:hidden">
              {q.data.items.map((i) => (
                <li key={i.id}><Link to={`/incidents/${i.id}`} className="block px-4 py-3">
                  <div className="flex flex-wrap items-center gap-1.5"><SeverityBadge severity={i.severity} /><span className="mono font-semibold">{i.display_id}</span><StatusBadge status={i.status} /><SourceBadge source={i.source_type} compact /></div>
                  <div className="mt-1 text-[13px]">{i.title}</div>
                  <div className="mono mt-0.5 text-[11.5px] text-ink-2">{i.device?.display_id} · {elapsedSince(i.detected_at)}</div>
                  <div className="mt-1 text-[12px] text-accent-700">{i.next_step}</div>
                </Link></li>
              ))}
            </ul>
          </>
        )}
      </Panel>

      <MetricsPanel />
      <DrillPicker open={drillOpen} onOpenChange={setDrillOpen} scenarios={scenarios.data ?? []} onStart={(k) => startDrill.mutate(k)} pending={startDrill.isPending} />
    </div>
  );
}

export function MetricsPanel({ printable }: { printable?: boolean }) {
  const m = useMetrics();
  const [src, setSrc] = useState<SourceType>("SIMULATED");
  if (m.isLoading) return <Panel title="Recovery measurements"><LoadingBlock /></Panel>;
  if (m.error || !m.data) return <ErrorState error={m.error} />;
  const b = m.data.by_source[src];
  const drills = b.drills.filter((d) => d.repair_interval_s !== null);
  return (
    <Panel title="Recovery measurements" icon={<Timer className="h-4 w-4" />} sub="Per source. Simulated and real drills are never combined."
      actions={!printable && (
        <div className="flex rounded-lg border border-line p-0.5" role="tablist" aria-label="Data source">
          {(["SIMULATED", "LOCAL_LAB", "IMPORTED_SAMPLE"] as SourceType[]).map((s) => (
            <button key={s} role="tab" aria-selected={src === s} onClick={() => setSrc(s)}
              className={clsx("rounded-md px-2 py-1 text-[11.5px] font-medium", src === s ? "bg-nav text-white" : "text-ink-2 hover:text-ink")}>{s.replace("_", " ").toLowerCase()} ({m.data.by_source[s].incidents})</button>
          ))}
        </div>
      )}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {([["detection_latency_s", "Detection latency", "detection_latency"], ["acknowledgment_latency_s", "Acknowledgment latency", "acknowledgment_latency"], ["mttr_s", "MTTR: detection to verified recovery", "mttr"]] as const).map(([k, label, def]) => {
          const s = b[k];
          return (
            <div key={k} className="rounded-xl border border-line p-3">
              <div className="flex items-start justify-between gap-2"><div className="eyebrow">{label}</div><span title={m.data.definitions[def]} className="text-ink-3"><Info className="h-3.5 w-3.5" aria-label={m.data.definitions[def]} /></span></div>
              <div className="mt-1.5 flex items-baseline gap-3">
                <div><div className="text-[22px] font-semibold tabular-nums">{s.median !== null ? fmtDuration(s.median) : "—"}</div><div className="text-[11px] text-ink-2">median</div></div>
                <div><div className="text-[15px] font-medium tabular-nums text-ink-2">{s.mean !== null ? fmtDuration(s.mean) : "—"}</div><div className="text-[11px] text-ink-2">mean</div></div>
                <div className="ml-auto text-right"><div className="mono text-[15px]">{s.count}</div><div className="text-[11px] text-ink-2">samples</div></div>
              </div>
              <p className="mt-2 text-[11px] leading-snug text-ink-2">{m.data.definitions[def]}</p>
            </div>
          );
        })}
      </div>
      {b.excluded_unknown_onset > 0 && <p className="mt-2 text-[12px] text-warn">{b.excluded_unknown_onset} incident(s) excluded from detection latency: fault onset unknown.</p>}
      {drills.length > 1 && (
        <div className="mt-4 h-[150px]" aria-hidden>
          <ResponsiveContainer>
            <BarChart data={drills.map((d) => ({ name: d.incident, mttr: Number(d.repair_interval_s?.toFixed(1)) }))} margin={{ left: -18, right: 8, top: 4 }}>
              <CartesianGrid vertical={false} stroke="#E9EDF2" />
              <XAxis dataKey="name" tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }} stroke="#C7D0DB" />
              <YAxis tick={{ fontSize: 10 }} stroke="#C7D0DB" unit="s" />
              <Tooltip cursor={{ fill: "#F5F7FA" }} contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: "#DDE3EA" }} formatter={(v) => [`${v} s`, "Detection → verified recovery"]} />
              <Bar dataKey="mttr" fill="#087F8C" radius={[3, 3, 0, 0]} maxBarSize={28} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="mt-3 overflow-x-auto">
        {b.drills.length === 0 ? <p className="text-[12.5px] text-ink-2">No {src.replace("_", " ").toLowerCase()} incidents recorded yet. Nothing is shown rather than an invented value.</p> : (
          <table className="table">
            <caption className="sr-only">Individual drill results</caption>
            <thead><tr><th>Incident</th><th>Scenario</th><th>Status</th><th className="text-right">Detection</th><th className="text-right">Acknowledgment</th><th className="text-right">Detection → verified</th></tr></thead>
            <tbody>
              {b.drills.map((d) => (
                <tr key={d.id}>
                  <td className="mono"><Link className="hover:text-accent-700" to={`/incidents/${d.id}`}>{d.incident}</Link></td><td className="mono text-ink-2">{d.scenario ?? "—"}</td><td><StatusBadge status={d.status} /></td>
                  <td className="mono text-right">{d.detection_latency_s !== null ? fmtDuration(d.detection_latency_s) : <span className="text-ink-3" title={d.detection_latency_note ?? ""}>Unavailable</span>}</td>
                  <td className="mono text-right">{fmtDuration(d.acknowledgment_latency_s)}</td>
                  <td className="mono text-right">{d.repair_interval_s !== null ? fmtDuration(d.repair_interval_s) : <span className="text-ink-3">Not resolved</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {!printable && <p className="mt-3 flex items-center gap-1 text-[11.5px] text-ink-2"><ArrowRight className="h-3 w-3" aria-hidden />No improvement percentages are shown. A comparison needs a recorded baseline and later runs of the same scenario.</p>}
    </Panel>
  );
}
