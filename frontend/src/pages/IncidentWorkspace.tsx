import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import {
  BookOpen, Check, ChevronDown, CircleCheck, CircleX, Download, FileJson, Hammer, Loader2, MessageSquarePlus, RotateCcw, ShieldCheck,
  Stethoscope, TerminalSquare, Timer, X,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, post } from "@/api/client";
import { useQuery } from "@tanstack/react-query";
import { useAction, useIncident, useIncidentSeries, useRunbooks } from "@/api/hooks";
import type { Evidence, IncidentDetail } from "@/api/types";
import { HealthDot, Pill, SeverityBadge, SourceBadge, StatusBadge } from "@/components/ui/Badges";
import { CopyButton, Empty, ErrorState, KV, LoadingBlock, Modal, Panel } from "@/components/ui/Primitives";
import { fmtDateTime, fmtDuration, fmtTime, human } from "@/lib/format";
import { Markdown } from "@/components/ui/Markdown";

const LIFECYCLE = ["detected", "acknowledged", "investigating", "repair_applied", "verification", "resolved"] as const;

function Stepper({ status }: { status: string }) {
  const idx = LIFECYCLE.indexOf(status as (typeof LIFECYCLE)[number]);
  return (
    <ol className="flex w-full items-center" aria-label={`Lifecycle: ${human(status)}`}>
      {LIFECYCLE.map((s, i) => {
        const done = i < idx || status === "resolved";
        const cur = i === idx && status !== "resolved";
        return (
          <li key={s} className="flex flex-1 items-center last:flex-none">
            <div className="flex flex-col items-center gap-1">
              <motion.span initial={false} animate={{ scale: cur ? 1.12 : 1 }}
                className={clsx("grid h-6 w-6 place-items-center rounded-full border-2 text-[10px] font-bold transition-colors duration-200",
                  done ? "border-accent bg-accent text-white" : cur ? "border-accent bg-white text-accent shadow-focus" : "border-line-strong bg-white text-ink-3")}
                aria-current={cur ? "step" : undefined}>
                {done ? <Check className="h-3.5 w-3.5" aria-hidden /> : i + 1}
              </motion.span>
              <span className={clsx("hidden whitespace-nowrap text-[10.5px] font-medium capitalize sm:block", cur ? "text-accent-700" : done ? "text-ink" : "text-ink-3")}>{s.replace("_", " ")}</span>
            </div>
            {i < LIFECYCLE.length - 1 && (
              <div className="relative mx-1 mb-0 h-[2px] flex-1 overflow-hidden rounded bg-line sm:mb-4">
                <motion.div className="absolute inset-y-0 left-0 bg-accent" initial={false} animate={{ width: i < idx || status === "resolved" ? "100%" : "0%" }} transition={{ duration: 0.4 }} />
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}

const EVENT_STYLE: Record<string, string> = {
  fault_onset: "bg-crit", detected: "bg-crit", status: "bg-accent", evidence: "bg-[#5DB3BC]", hypothesis: "bg-sim",
  repair: "bg-warn", verification: "bg-ok", reopened: "bg-warn", note: "bg-ink-3", resolved: "bg-ok",
};

function Timeline({ inc }: { inc: IncidentDetail }) {
  const [note, setNote] = useState("");
  const add = useAction(() => post(`/incidents/${inc.id}/notes`, { text: note }), { onSuccess: () => setNote("") });
  return (
    <Panel title="Investigation timeline" icon={<Timer className="h-4 w-4" />} sub="UTC · append-only" bodyClass="p-0">
      <ol className="relative max-h-[560px] space-y-0 overflow-y-auto px-4 py-3">
        <div className="absolute bottom-3 left-[27px] top-3 w-px bg-line" aria-hidden />
        <AnimatePresence initial={false}>
          {inc.events.map((e) => {
            const ver = e.kind === "verification" ? (e.detail as { passed?: boolean; waiting?: boolean }) : null;
            const dot = ver ? (ver.passed ? "bg-ok" : ver.waiting ? "bg-warn" : "bg-crit") : e.to_status === "resolved" ? "bg-ok" : EVENT_STYLE[e.kind] ?? "bg-ink-3";
            return (
              <motion.li key={e.id} layout initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.22 }} className="relative flex gap-3 pb-3.5">
                <span className={clsx("relative z-10 mt-1 h-[9px] w-[9px] shrink-0 translate-x-[7px] rounded-full ring-4 ring-white", dot)} aria-hidden />
                <div className="ml-2 min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-x-2">
                    <span className="mono text-[11.5px] text-ink-2">{fmtTime(e.occurred_at)}</span>
                    <span className="text-2xs font-semibold uppercase tracking-wider text-ink-3">{e.kind.replace("_", " ")}</span>
                    <span className="text-[11px] text-ink-3">{e.actor}</span>
                  </div>
                  <div className={clsx("text-[13px] leading-snug", ver && !ver.passed && !ver.waiting ? "text-crit" : "text-ink")}>{e.summary}</div>
                  {e.kind === "evidence" && typeof e.detail.evidence === "string" && <a href={`#ev-${e.detail.evidence_id}`} className="mono text-[11px] text-accent-700 hover:underline">{e.detail.evidence as string}</a>}
                </div>
              </motion.li>
            );
          })}
        </AnimatePresence>
      </ol>
      {inc.status !== "resolved" && (
        <form className="flex gap-2 border-t border-line-soft p-3" onSubmit={(e) => { e.preventDefault(); if (note.trim()) add.mutate(); }}>
          <label htmlFor="note" className="sr-only">Add investigation note</label>
          <input id="note" className="input h-8" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add an investigation note…" maxLength={4000} />
          <button className="btn-secondary h-8" disabled={!note.trim() || add.isPending}><MessageSquarePlus className="h-3.5 w-3.5" aria-hidden />Add</button>
        </form>
      )}
    </Panel>
  );
}

function EvidenceItem({ e, open, onToggle }: { e: Evidence; open: boolean; onToggle: () => void }) {
  return (
    <li id={`ev-${e.id}`} className="scroll-mt-20 rounded-xl border border-line bg-white">
      <button className="flex w-full items-center gap-2 px-3 py-2.5 text-left" onClick={onToggle} aria-expanded={open}>
        <TerminalSquare className="h-4 w-4 shrink-0 text-ink-3" aria-hidden />
        <span className="mono font-medium text-ink">{e.collector}</span>
        <span className="mono text-[11px] text-ink-3">{e.display_id} · {fmtTime(e.collected_at)}</span>
        <ChevronDown className={clsx("ml-auto h-4 w-4 text-ink-3 transition-transform duration-200", open && "rotate-180")} aria-hidden />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden">
            <div className="space-y-2 border-t border-line-soft px-3 pb-3 pt-2">
              <div className="flex items-center justify-between gap-2">
                <code className="mono truncate text-[11.5px] text-ink-2">$ {e.command}</code>
                <CopyButton text={e.output} label="Copy output" />
              </div>
              <pre className="pre max-h-[260px]">{e.output}</pre>
              <div className="rounded-lg bg-accent-50/60 px-3 py-2">
                <div className="eyebrow text-accent-700">Observed (interpretation of output)</div>
                <p className="text-[12.5px] text-ink">{e.interpretation}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-[11px] text-ink-2">
                <SourceBadge source={e.source_type} /><span className="mono break-all">{e.source_id}</span>
                <span className="mono">collected {fmtDateTime(e.collected_at)}</span>
              </div>
              {e.limitations && <p className="text-[11.5px] italic text-ink-2">Limitations: {e.limitations}</p>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </li>
  );
}

function MetricsChart({ inc }: { inc: IncidentDetail }) {
  const s = useIncidentSeries(String(inc.id));
  const metrics = useMemo(() => {
    const by: Record<string, { unit: string; pts: { t: number; v: number | null }[] }> = {};
    (s.data?.series ?? []).forEach((r) => {
      const key = r.labels?.psu ? `${r.metric}:${r.labels.psu}` : r.metric;
      (by[key] ??= { unit: r.unit, pts: [] }).pts.push({ t: new Date(r.observed_at).getTime(), v: r.value });
    });
    return by;
  }, [s.data]);
  const keys = Object.keys(metrics).filter((k) => !k.startsWith("psu_output"));
  const [sel, setSel] = useState<string | null>(null);
  const key = sel && metrics[sel] ? sel : keys[0];
  if (s.isLoading) return <LoadingBlock rows={4} />;
  if (!key) return <Empty title="No metric observations for this incident">Metrics come from the simulator's probes or from live-lab probes.</Empty>;
  const data = metrics[key].pts;
  const refs = [
    inc.fault_onset_at && { t: new Date(inc.fault_onset_at).getTime(), label: "onset", color: "#C93644" },
    { t: new Date(inc.detected_at).getTime(), label: "detected", color: "#A65D00" },
    ...inc.repairs.map((r) => ({ t: new Date(r.applied_at).getTime(), label: "repair", color: "#087F8C" })),
    inc.verified_at && { t: new Date(inc.verified_at).getTime(), label: "verified", color: "#18794E" },
  ].filter(Boolean) as { t: number; label: string; color: string }[];
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        {keys.map((k) => (
          <button key={k} onClick={() => setSel(k)} aria-pressed={k === key}
            className={clsx("mono h-6 rounded-md border px-2 text-[11px]", k === key ? "border-accent bg-accent-50 text-accent-700" : "border-line text-ink-2 hover:text-ink")}>{k} ({metrics[k].unit})</button>
        ))}
        <span className="ml-auto"><SourceBadge source={s.data?.source_type} /></span>
      </div>
      <div className="h-[190px]" role="img" aria-label={`Chart of ${key}; ${data.length} samples. Null values (not collected) appear as gaps, not zeros.`}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ left: -12, right: 12, top: 8, bottom: 0 }}>
            <CartesianGrid stroke="#EEF1F5" vertical={false} />
            <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(t) => fmtTime(new Date(t).toISOString()).slice(3, 8)} tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }} stroke="#C7D0DB" />
            <YAxis tick={{ fontSize: 10 }} stroke="#C7D0DB" width={44} />
            <Tooltip labelFormatter={(t) => fmtTime(new Date(Number(t)).toISOString())} formatter={(v) => [v === null ? "Not collected" : `${v} ${metrics[key].unit}`, key]}
              contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: "#DDE3EA" }} />
            {refs.map((r, i) => <ReferenceLine key={i} x={r.t} stroke={r.color} strokeDasharray="4 3" label={{ value: r.label, position: "insideTopRight", fontSize: 10, fill: r.color }} />)}
            <Line type="stepAfter" dataKey="v" stroke="#087F8C" strokeWidth={2} dot={false} isAnimationActive connectNulls={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <details className="mt-2 text-[12px]"><summary className="cursor-pointer text-ink-2">Table of values ({data.length})</summary>
        <div className="mt-1 max-h-40 overflow-auto"><table className="table"><thead><tr><th>Time</th><th>{key}</th></tr></thead><tbody>
          {data.slice(-30).map((p) => <tr key={p.t}><td className="mono">{fmtTime(new Date(p.t).toISOString())}</td><td className="mono">{p.v === null ? "Not collected" : p.v}</td></tr>)}
        </tbody></table></div>
      </details>
    </div>
  );
}

export function IncidentWorkspace() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const q = useIncident(id);
  const runbooks = useRunbooks();
  const [openEv, setOpenEv] = useState<number | null>(null);
  const [repairConfirm, setRepairConfirm] = useState<IncidentDetail["repair_options"][number] | null>(null);
  const [reopenOpen, setReopenOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [resolveOpen, setResolveOpen] = useState(false);
  const [rootCause, setRootCause] = useState("");
  const tab = params.get("tab") ?? "workspace";

  const act = (path: string, body?: unknown) => post(`/incidents/${id}/${path}`, body);
  const transition = useAction((action: "acknowledge" | "investigate") => act("transition", { action }));
  const collect = useAction((collector: string) => post<Evidence>(`/incidents/${id}/evidence`, { collector }), { onSuccess: (e) => setOpenEv(e.id) });
  const hyp = useAction((v: { key: string; status: string }) => act(`hypotheses/${v.key}`, { status: v.status, note: "" }));
  const repair = useAction((key: string) => act("repair", { action_key: key }), { success: "Repair recorded. Now run verification.", onSuccess: () => setRepairConfirm(null) });
  const verify = useAction(() => post<IncidentDetail>(`/incidents/${id}/verify`), {
    success: (r) => { const v = r.verifications.at(-1); return v?.passed ? "Verification passed. Recovery confirmed." : undefined; },
  });
  const resolve = useAction(() => act("resolve", { root_cause: rootCause }), { success: "Incident resolved", onSuccess: () => { setResolveOpen(false); setParams({ tab: "summary" }); } });
  const reopen = useAction(() => act("reopen", { reason }), { success: "Incident reopened. Prior history is preserved.", onSuccess: () => { setReopenOpen(false); setReason(""); } });

  if (q.isLoading) return <LoadingBlock rows={12} label="Loading incident" />;
  if (q.error || !q.data) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const inc = q.data;
  const rb = runbooks.data?.find((r) => r.slug === inc.runbook_slug);
  const lastVer = inc.verifications.at(-1);
  const collected = new Set(inc.evidence.map((e) => e.collector));
  const busy = transition.isPending || verify.isPending || repair.isPending || resolve.isPending;
  const needsSpare = inc.repair_options.some((r) => r.requires_spare_workflow);
  const verWaiting = lastVer && !lastVer.passed && lastVer.checks.every((c) => c.passed || c.key === "post_repair_samples");

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="panel overflow-hidden">
        <div className={clsx("h-1", inc.status === "resolved" ? "bg-ok" : inc.severity === "critical" ? "bg-crit" : "bg-warn")} aria-hidden />
        <div className="flex flex-col gap-4 p-4 md:p-5">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="mono text-[13px] font-semibold text-ink-2">{inc.display_id}</span>
                <SeverityBadge severity={inc.severity} /><StatusBadge status={inc.status} /><SourceBadge source={inc.source_type} />
                {inc.reopen_count > 0 && <Pill className="border-warn/30 bg-warn-50 text-warn">reopened ×{inc.reopen_count}</Pill>}
              </div>
              <h1 className="mt-1.5 text-[21px] font-semibold leading-tight text-ink md:text-[23px]">{inc.title}</h1>
              <p className="mt-1 text-[13px] text-ink-2">{inc.symptom}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {inc.status === "detected" && <button className="btn-primary" disabled={busy} onClick={() => transition.mutate("acknowledge")}><Check className="h-4 w-4" aria-hidden />Acknowledge</button>}
              {inc.status === "acknowledged" && <button className="btn-primary" disabled={busy} onClick={() => transition.mutate("investigate")}><Stethoscope className="h-4 w-4" aria-hidden />Start investigation</button>}
              {(inc.status === "repair_applied" || (inc.status === "verification" && !lastVer?.passed)) && (
                <button className="btn-primary" disabled={busy} onClick={() => verify.mutate()}>{verify.isPending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <ShieldCheck className="h-4 w-4" aria-hidden />}Run verification</button>
              )}
              {inc.status === "verification" && lastVer?.passed && <button className="btn-primary bg-ok hover:bg-ok/90" disabled={busy} onClick={() => setResolveOpen(true)}><CircleCheck className="h-4 w-4" aria-hidden />Resolve</button>}
              {inc.status === "resolved" && <button className="btn-secondary" onClick={() => setReopenOpen(true)}><RotateCcw className="h-4 w-4" aria-hidden />Reopen</button>}
              <div className="flex rounded-lg border border-line p-0.5" role="tablist">
                {[["workspace", "Workspace"], ["summary", "Summary"]].map(([v, l]) => (
                  <button key={v} role="tab" aria-selected={tab === v} onClick={() => setParams({ tab: v })} className={clsx("rounded-md px-2.5 py-1 text-[12px] font-medium", tab === v ? "bg-nav text-white" : "text-ink-2 hover:text-ink")}>{l}</button>
                ))}
              </div>
            </div>
          </div>
          <Stepper status={inc.status} />
        </div>
      </div>

      {tab === "summary" ? <SummaryView id={inc.id} display={inc.display_id} /> : (
        <>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[300px_minmax(0,1fr)_380px]">
            {/* Left */}
            <div className="space-y-4">
              <Panel title="Summary">
                <dl className="divide-y divide-line-soft">
                  <KV k="Device" v={inc.device ? <Link className="mono text-accent-700 hover:underline" to={`/infrastructure?device=${inc.device.display_id}`}>{inc.device.display_id}</Link> : "Unknown"} />
                  {inc.device && <KV k="Health" v={<HealthDot health={inc.device.health} />} />}
                  <KV k="Location" v={inc.device?.rack ? `${inc.device.rack} U${inc.device.position_u}` : "—"} mono />
                  <KV k="Fault onset" v={inc.fault_onset_at ? fmtTime(inc.fault_onset_at) : <span className="text-warn">Unknown</span>} mono />
                  <KV k="Detected" v={fmtTime(inc.detected_at)} mono />
                  <KV k="Acknowledged" v={fmtTime(inc.acknowledged_at)} mono />
                  <KV k="Verified" v={fmtTime(inc.verified_at)} mono />
                  <KV k="Assigned" v={inc.assigned_operator ?? "Unassigned"} />
                </dl>
                <div className="mt-3 rounded-lg bg-canvas p-2.5">
                  <div className="eyebrow">Detection rule</div>
                  <p className="mono mt-0.5 text-[11px] leading-snug text-ink">{inc.detection_rule}</p>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                  {([["Detect", inc.metrics.detection_latency_s], ["Ack", inc.metrics.acknowledgment_latency_s], ["→ Verified", inc.metrics.repair_interval_s]] as const).map(([l, v]) => (
                    <div key={l} className="rounded-lg border border-line-soft p-1.5">
                      <div className={clsx("mono text-[12.5px] font-semibold", v === null ? "text-ink-3" : "text-ink")}>{v === null ? "n/a" : fmtDuration(v)}</div>
                      <div className="text-[10px] text-ink-2">{l}</div>
                    </div>
                  ))}
                </div>
                {inc.metrics.detection_latency_note && <p className="mt-1.5 text-[11px] text-warn">{inc.metrics.detection_latency_note}</p>}
              </Panel>

              <Panel title="Hypotheses" icon={<Stethoscope className="h-4 w-4" />} sub="Diagnosis, kept separate from evidence">
                <ul className="space-y-2.5">
                  {inc.hypotheses.map((h) => (
                    <li key={h.key} className={clsx("rounded-xl border p-2.5 transition-colors", h.status === "supported" ? "border-ok/40 bg-ok-50/50" : h.status === "refuted" ? "border-line bg-canvas opacity-75" : "border-line")}>
                      <div className="flex items-start gap-2">
                        {h.status === "supported" ? <CircleCheck className="mt-0.5 h-4 w-4 shrink-0 text-ok" aria-label="Supported" /> : h.status === "refuted" ? <CircleX className="mt-0.5 h-4 w-4 shrink-0 text-ink-3" aria-label="Refuted" /> : <span className="mt-1 h-3 w-3 shrink-0 rounded-full border-2 border-line-strong" aria-label="Open" />}
                        <div className="min-w-0">
                          <p className={clsx("text-[12.5px] font-medium", h.status === "refuted" && "line-through decoration-ink-3")}>{h.statement}</p>
                          <p className="mt-0.5 text-[11.5px] text-ink-2"><b className="font-medium">Discriminating check:</b> {h.discriminating_check}</p>
                          {h.note && <p className="mt-0.5 text-[11.5px] italic text-ink-2">{h.note}</p>}
                        </div>
                      </div>
                      {inc.status !== "resolved" && (
                        <div className="mt-2 flex gap-1 pl-6">
                          {(["supported", "refuted", "open"] as const).filter((s) => s !== h.status).map((s) => (
                            <button key={s} className="btn-ghost btn-sm h-6 px-2 text-[11px] capitalize" onClick={() => hyp.mutate({ key: h.key, status: s })}>{s === "open" ? "Reset" : `Mark ${s}`}</button>
                          ))}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </Panel>
            </div>

            {/* Center */}
            <div className="min-w-0 space-y-4">
              <Timeline inc={inc} />
            </div>

            {/* Right */}
            <div className="min-w-0 space-y-4">
              <Panel title="Evidence" icon={<TerminalSquare className="h-4 w-4" />} sub={`${inc.evidence.length} item(s) collected`}>
                {inc.collectors.length > 0 && inc.status !== "resolved" && (
                  <div className="mb-3">
                    <div className="eyebrow mb-1.5">Collect</div>
                    <div className="flex flex-wrap gap-1.5">
                      {inc.collectors.map((c) => (
                        <button key={c.key} onClick={() => collect.mutate(c.key)} disabled={collect.isPending || !["investigating", "repair_applied", "verification", "acknowledged"].includes(inc.status)}
                          title={inc.status === "detected" ? "Acknowledge first" : c.label}
                          className={clsx("mono inline-flex h-7 items-center gap-1 rounded-md border px-2 text-[11px] transition-colors disabled:opacity-40",
                            c.recommended ? "border-accent/40 bg-accent-50 text-accent-700 hover:bg-accent-100" : "border-line text-ink-2 hover:bg-canvas")}>
                          {collected.has(c.key) && <Check className="h-3 w-3" aria-label="collected" />}{c.key}
                        </button>
                      ))}
                    </div>
                    <p className="mt-1.5 text-[11px] text-ink-2">Highlighted collectors are recommended by the runbook.</p>
                  </div>
                )}
                {inc.evidence.length === 0 ? <p className="text-[12.5px] text-ink-2">No evidence collected yet.</p> : (
                  <ul className="space-y-2">
                    {[...inc.evidence].reverse().map((e) => <EvidenceItem key={e.id} e={e} open={openEv === e.id} onToggle={() => setOpenEv(openEv === e.id ? null : e.id)} />)}
                  </ul>
                )}
              </Panel>

              {rb && (
                <Panel title={rb.title} icon={<BookOpen className="h-4 w-4" />} sub={`Runbook v${rb.version}`} actions={<Link to={`/runbooks/${rb.slug}`} className="btn-ghost btn-sm">Open</Link>}>
                  <ol className="space-y-2">
                    {rb.sections.investigation.map((s: any, i: number) => {
                      const done = s.collector && collected.has(s.collector);
                      return (
                        <li key={i} className="flex gap-2 text-[12.5px]">
                          <span className={clsx("mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border text-[9px] font-bold", done ? "border-ok bg-ok text-white" : "border-line-strong text-ink-3")}>{done ? <Check className="h-2.5 w-2.5" /> : i + 1}</span>
                          <div><div className="font-medium text-ink">{s.step}</div><div className="text-[11.5px] text-ink-2">{s.why}</div>
                            {s.collector && !done && inc.status !== "resolved" && <button className="mono mt-0.5 text-[11px] text-accent-700 hover:underline" onClick={() => collect.mutate(s.collector)}>collect {s.collector}</button>}
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                  <div className="mt-3 border-t border-line-soft pt-2">
                    <div className="eyebrow mb-1">Decision points</div>
                    <ul className="space-y-1 text-[11.5px] text-ink-2">{rb.sections.decision_points.map((d: string) => <li key={d}>• {d}</li>)}</ul>
                    <div className="eyebrow mb-1 mt-2">Escalate when</div>
                    <ul className="space-y-1 text-[11.5px] text-ink-2">{rb.sections.escalation.map((d: string) => <li key={d}>• {d}</li>)}</ul>
                  </div>
                </Panel>
              )}
            </div>
          </div>

          {/* Lower */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
            <Panel title="Metrics" sub="Fault onset, detection, repair and verification are marked">
              <MetricsChart inc={inc} />
            </Panel>
            <div className="space-y-4">
              <Panel title="Corrective action" icon={<Hammer className="h-4 w-4" />}>
                {inc.status === "investigating" ? (
                  needsSpare ? (
                    <div className="space-y-2">
                      <p className="text-[12.5px] text-ink-2">This repair replaces a physical component, so it is recorded through the spare-parts workflow (reserve, then consume). That keeps inventory and returns reconciled.</p>
                      <button className="btn-primary" onClick={() => nav(`/spares?device=${inc.device?.id}&incident=${inc.id}`)}>Open spare-parts workflow</button>
                    </div>
                  ) : (
                    <ul className="space-y-2">
                      {inc.repair_options.map((r) => (
                        <li key={r.key} className="flex items-start gap-3 rounded-xl border border-line p-2.5">
                          <div className="min-w-0 flex-1">
                            <div className="text-[13px] font-medium">{r.label}</div>
                            <div className="text-[11.5px] text-ink-2">{r.description}</div>
                            {r.tests_hypothesis && <div className="mono mt-0.5 text-[10.5px] text-ink-3">tests: {r.tests_hypothesis}</div>}
                          </div>
                          <button className="btn-secondary btn-sm" onClick={() => setRepairConfirm(r)}>Apply</button>
                        </li>
                      ))}
                    </ul>
                  )
                ) : (
                  <p className="text-[12.5px] text-ink-2">{inc.status === "resolved" ? "Incident resolved." : inc.status === "detected" || inc.status === "acknowledged" ? "Acknowledge and start the investigation before recording a repair." : "Repair recorded. Run verification to confirm recovery."}</p>
                )}
                {inc.repairs.length > 0 && (
                  <div className="mt-3 border-t border-line-soft pt-2">
                    <div className="eyebrow mb-1">Applied</div>
                    <ul className="space-y-1">{inc.repairs.map((r) => <li key={r.id} className="text-[12px]"><span className="mono text-ink-3">{fmtTime(r.applied_at)}</span> {r.description}</li>)}</ul>
                  </div>
                )}
              </Panel>

              <Panel title="Verification" icon={<ShieldCheck className="h-4 w-4" />} sub="Recovery must be demonstrated by checks, not asserted">
                {!lastVer ? <p className="text-[12.5px] text-ink-2">No verification run yet.</p> : (
                  <div>
                    <div className="mb-2 flex items-center gap-2">
                      {lastVer.passed ? <Pill className="border-ok/30 bg-ok-50 text-ok"><CircleCheck className="h-3 w-3" aria-hidden />PASSED</Pill> : verWaiting ? <Pill className="border-warn/30 bg-warn-50 text-warn">WAITING FOR SAMPLES</Pill> : <Pill className="border-crit/30 bg-crit-50 text-crit"><X className="h-3 w-3" aria-hidden />FAILED</Pill>}
                      <span className="mono text-[11.5px] text-ink-2">{fmtDateTime(lastVer.executed_at)}</span>
                      <SourceBadge source={lastVer.source_type} compact />
                    </div>
                    <ul className="space-y-1.5">
                      {lastVer.checks.map((c) => (
                        <motion.li key={c.key} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} className="flex items-start gap-2 text-[12.5px]">
                          {c.passed ? <CircleCheck className="mt-0.5 h-4 w-4 shrink-0 text-ok" aria-label="passed" /> : <CircleX className={clsx("mt-0.5 h-4 w-4 shrink-0", c.key === "post_repair_samples" ? "text-warn" : "text-crit")} aria-label="not passed" />}
                          <div className="min-w-0"><div>{c.name}</div><div className="mono text-[11px] text-ink-2">observed {c.observed} · expected {c.expected}</div></div>
                        </motion.li>
                      ))}
                    </ul>
                    {inc.simulation && !lastVer.passed && <p className="mt-2 text-[11.5px] text-ink-2">Healthy probes since last repair: <b className="mono">{inc.simulation.healthy_since_repair}</b> / 2</p>}
                    {inc.verifications.length > 1 && <p className="mt-2 text-[11px] text-ink-3">{inc.verifications.length - 1} earlier verification(s) kept in the timeline.</p>}
                  </div>
                )}
              </Panel>
            </div>
          </div>
        </>
      )}

      <Modal open={!!repairConfirm} onOpenChange={(o) => !o && setRepairConfirm(null)} title="Record corrective action" description={inc.source_type === "SIMULATED" ? "Simulated action: changes only the simulator's state." : "This performs a real action on the lab-owned target."}>
        <p className="text-[13px] font-medium">{repairConfirm?.label}</p>
        <p className="mt-1 text-[12.5px] text-ink-2">{repairConfirm?.description}</p>
        <p className="mt-3 rounded-lg bg-canvas p-2.5 text-[12px] text-ink-2">After recording the repair, run verification. A wrong fix will fail verification, and the incident returns to investigation.</p>
        <div className="mt-4 flex justify-end gap-2"><button className="btn-secondary" onClick={() => setRepairConfirm(null)}>Cancel</button><button className="btn-primary" disabled={repair.isPending} onClick={() => repairConfirm && repair.mutate(repairConfirm.key)}>Record repair</button></div>
      </Modal>
      <Modal open={resolveOpen} onOpenChange={setResolveOpen} title="Resolve incident" description="Verification passed after the most recent repair.">
        <label className="label" htmlFor="rc">Root cause (optional: defaults to the scenario's documented cause)</label>
        <textarea id="rc" className="input" rows={3} value={rootCause} onChange={(e) => setRootCause(e.target.value)} />
        <div className="mt-4 flex justify-end gap-2"><button className="btn-secondary" onClick={() => setResolveOpen(false)}>Cancel</button><button className="btn-primary" disabled={resolve.isPending} onClick={() => resolve.mutate()}>Resolve</button></div>
      </Modal>
      <Modal open={reopenOpen} onOpenChange={setReopenOpen} title="Reopen incident" description="History, verifications and repairs are preserved.">
        <label className="label" htmlFor="rr">Reason</label>
        <textarea id="rr" className="input" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Probe failed again 10 minutes after resolution" />
        <div className="mt-4 flex justify-end gap-2"><button className="btn-secondary" onClick={() => setReopenOpen(false)}>Cancel</button><button className="btn-primary" disabled={reason.trim().length < 3 || reopen.isPending} onClick={() => reopen.mutate()}>Reopen</button></div>
      </Modal>
    </div>
  );
}

function SummaryView({ id, display }: { id: number; display: string }) {
  const sq = useQuery({ queryKey: ["incident", String(id), "summary"], queryFn: () => api<{ markdown: string }>(`/incidents/${id}/summary`) });
  const md = sq.data?.markdown ?? null;
  return (
    <Panel title="Post-incident summary" sub="Generated from stored records only"
      actions={<>
        <a className="btn-secondary btn-sm" href={`/api/incidents/${id}/summary.md`} download><Download className="h-3.5 w-3.5" aria-hidden />Markdown</a>
        <a className="btn-secondary btn-sm" href={`/api/incidents/${id}/export/jira`} download><FileJson className="h-3.5 w-3.5" aria-hidden />Jira payload</a>
        <button className="btn-ghost btn-sm" onClick={() => window.print()}>Print</button>
      </>}>
      {md === null ? <LoadingBlock rows={10} /> : <article className="max-w-3xl" aria-label={`Summary for ${display}`}><Markdown text={md} /></article>}
    </Panel>
  );
}
