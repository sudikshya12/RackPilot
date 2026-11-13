import clsx from "clsx";
import { motion } from "framer-motion";
import { ChevronRight, Info, PlayCircle, Save, Undo2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { patch } from "@/api/client";
import { useAction, useReturns } from "@/api/hooks";
import type { ReturnRecord } from "@/api/types";
import { LifecycleBadge, Pill } from "@/components/ui/Badges";
import { Empty, ErrorState, LoadingBlock, PageHeader, Panel } from "@/components/ui/Primitives";
import { fmtDateTime, human } from "@/lib/format";

const FLOW = ["awaiting_reference", "ready_to_ship", "shipped", "received_by_vendor", "closed"] as const;

function warranty(w: string) {
  return w === "known_active" ? "Active (known)" : w === "known_expired" ? "Expired (known)" : "Unknown";
}

function ShippingProgress({ status }: { status: string }) {
  const idx = FLOW.indexOf(status as (typeof FLOW)[number]);
  return (
    <div aria-label={`Shipping status: ${human(status)} (step ${idx + 1} of ${FLOW.length})`}>
      <div className="flex items-center gap-1" aria-hidden>
        {FLOW.map((s, i) => (
          <div key={s} className="h-1.5 flex-1 overflow-hidden rounded-full bg-line">
            <motion.div className={clsx("h-full rounded-full", i === FLOW.length - 1 && idx === i ? "bg-ok" : "bg-accent")}
              initial={false} animate={{ width: i <= idx ? "100%" : "0%" }} transition={{ duration: 0.3, delay: i * 0.05 }} />
          </div>
        ))}
      </div>
      <div className="mt-1 hidden grid-cols-5 gap-1 text-[10px] text-ink-3 sm:grid" aria-hidden>
        {FLOW.map((s, i) => <span key={s} className={clsx("truncate", i === idx && "font-semibold text-accent-700")}>{human(s)}</span>)}
      </div>
    </div>
  );
}

function ReturnCard({ r, index }: { r: ReturnRecord; index: number }) {
  const [ref, setRef] = useState(r.return_reference ?? "");
  useEffect(() => setRef(r.return_reference ?? ""), [r.return_reference]);
  const idx = FLOW.indexOf(r.shipping_status as (typeof FLOW)[number]);
  const next = idx >= 0 && idx < FLOW.length - 1 ? FLOW[idx + 1] : null;
  const saveRef = useAction(() => patch(`/returns/${r.id}`, { return_reference: ref }), { success: `Reference saved on ${r.display_id}` });
  const advance = useAction(() => patch(`/returns/${r.id}`, { shipping_status: next }), { success: `${r.display_id} → ${human(next)}` });
  const dirty = ref.trim() !== (r.return_reference ?? "");

  return (
    <motion.li initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22, delay: Math.min(index * 0.04, 0.24) }}
      className="panel p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="mono text-[14px] font-semibold text-ink">{r.display_id}</span>
        <Pill className={r.shipping_status === "closed" ? "border-ok/30 bg-ok-50 text-ok" : "border-accent/30 bg-accent-50 text-accent-700"}>{human(r.shipping_status)}</Pill>
        {r.origin === "simulation" && <Pill className="border-sim/25 bg-sim-50 text-sim">simulation</Pill>}
        <span className="mono ml-auto text-[11.5px] text-ink-3">opened {fmtDateTime(r.created_at)} by {r.actor}</span>
      </div>

      <div className="mt-3 grid gap-4 md:grid-cols-3">
        <dl className="space-y-1.5 text-[12.5px]">
          <div><dt className="eyebrow">Failed asset</dt>
            <dd className="mt-0.5 flex flex-wrap items-center gap-1.5"><Link className="mono font-medium text-accent-700 hover:underline" to={`/assets/${r.failed_asset.id}`}>{r.failed_asset.display_id}</Link>
              <LifecycleBadge status={r.failed_asset.status} /></dd>
            <dd className="mono text-[11.5px] text-ink-2">{r.failed_asset.serial_number} · {r.failed_asset.model}</dd></div>
          <div><dt className="eyebrow">Original device</dt>
            <dd>{r.original_device ? <Link className="mono text-accent-700 hover:underline" to={`/infrastructure?device=${r.original_device.display_id}`}>{r.original_device.display_id}</Link> : "—"}</dd></div>
          <div><dt className="eyebrow">Replacement</dt>
            <dd>{r.replacement_asset ? <Link className="mono text-accent-700 hover:underline" to={`/assets/${r.replacement_asset.id}`}>{r.replacement_asset.display_id} ({r.replacement_asset.serial_number})</Link> : <span className="text-ink-3">Not linked</span>}</dd></div>
        </dl>
        <dl className="space-y-1.5 text-[12.5px]">
          <div><dt className="eyebrow">Failure summary</dt><dd className="mt-0.5 text-ink">{r.failure_summary}</dd></div>
          <div><dt className="eyebrow">Incident</dt><dd>{r.incident_id ? <Link className="mono text-accent-700 hover:underline" to={`/incidents/${r.incident_id}`}>#{r.incident_id}</Link> : "—"}
            {r.failure_evidence_id && <span className="mono ml-2 text-[11px] text-ink-2">evidence #{r.failure_evidence_id}</span>}</dd></div>
          <div><dt className="eyebrow">Warranty</dt><dd className={clsx(r.warranty_status === "unknown" && "text-warn")}>{warranty(r.warranty_status)}</dd></div>
        </dl>
        <div className="space-y-3">
          <form onSubmit={(e) => { e.preventDefault(); if (dirty) saveRef.mutate(); }}>
            <label className="label" htmlFor={`ref-${r.id}`}>Vendor return reference</label>
            <div className="flex gap-1.5">
              <input id={`ref-${r.id}`} className="input mono h-8" value={ref} onChange={(e) => setRef(e.target.value)} placeholder="Entered by operator" maxLength={64}
                disabled={r.shipping_status === "closed"} />
              <button className="btn-secondary h-8" disabled={!dirty || saveRef.isPending} aria-label={`Save return reference for ${r.display_id}`}><Save className="h-3.5 w-3.5" aria-hidden />Save</button>
            </div>
          </form>
          <ShippingProgress status={r.shipping_status} />
          {next ? (
            <button className="btn-primary btn-sm" disabled={advance.isPending} onClick={() => advance.mutate()}>
              Advance to {human(next)}<ChevronRight className="h-3.5 w-3.5" aria-hidden />
            </button>
          ) : <p className="text-[12px] text-ok">Return closed. Failed asset marked returned.</p>}
          {next === "ready_to_ship" && !r.return_reference && <p className="text-[11.5px] text-ink-2">A vendor reference is required before the part is ready to ship.</p>}
        </div>
      </div>
    </motion.li>
  );
}

export function Returns() {
  const q = useReturns();
  return (
    <div className="space-y-5">
      <PageHeader title="Returns / RMA">Failed components awaiting return to the vendor.</PageHeader>
      <div className="flex items-start gap-2 rounded-xl border border-accent/30 bg-accent-50/60 px-4 py-3 text-[13px] text-ink" role="note">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-accent-700" aria-hidden />
        This queue records returns. It does not contact any vendor; references are entered by the operator.
      </div>
      {q.isLoading ? <Panel title="Returns"><LoadingBlock rows={5} /></Panel> : q.error ? <ErrorState error={q.error} retry={() => q.refetch()} /> : !q.data?.length ? (
        <Panel title="Returns" icon={<Undo2 className="h-4 w-4" />}>
          <Empty title="No returns recorded" icon={<Undo2 className="h-5 w-5" />}
            action={<Link to="/demo" className="btn-primary btn-sm"><PlayCircle className="h-3.5 w-3.5" aria-hidden />Run the replace-component demo</Link>}>
            A return record is created when a failed part is removed through the spare-parts workflow.
          </Empty>
        </Panel>
      ) : (
        <ul className="space-y-3" aria-label="Return records">
          {q.data.map((r, i) => <ReturnCard key={r.id} r={r} index={i} />)}
        </ul>
      )}
    </div>
  );
}
