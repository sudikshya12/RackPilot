import { motion } from "framer-motion";
import { ArrowRightLeft, History, Printer, Undo2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { post } from "@/api/client";
import { useAction, useAsset, useRacks } from "@/api/hooks";
import { AuditList, DevicePanel } from "@/components/rack/DevicePanel";
import { QrLabel } from "@/components/rack/QrLabel";
import { LifecycleBadge, Pill } from "@/components/ui/Badges";
import { ErrorState, KV, LoadingBlock, PageHeader, Panel } from "@/components/ui/Primitives";
import { fmtDateTime, human } from "@/lib/format";

function warranty(w: string) {
  return w === "known_active" ? "Active (known)" : w === "known_expired" ? "Expired (known)" : "Unknown";
}

function TransitionForm({ asset }: { asset: any }) {
  const racks = useRacks();
  const [to, setTo] = useState("");
  const [location, setLocation] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [note, setNote] = useState("");
  const allowed: string[] = asset.allowed_transitions ?? [];
  useEffect(() => { setTo(""); setLocation(""); setDeviceId(""); setNote(""); }, [asset.status]);
  const act = useAction(() => post(`/assets/${asset.id}/transition`, {
    to, location: location || null, device_id: deviceId ? Number(deviceId) : null, note,
  }), { success: `${asset.display_id} moved to ${human(to)}` });
  const devices = (racks.data ?? []).flatMap((r) => r.devices).filter((d) => d.role !== "pdu");

  if (!allowed.length) {
    return <p className="text-[12.5px] text-ink-2">{human(asset.status)} is a terminal state. No further transitions are allowed.</p>;
  }
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (to) act.mutate(); }}>
      <div>
        <label className="label" htmlFor="tr-to">Move to</label>
        <select id="tr-to" className="input" value={to} onChange={(e) => setTo(e.target.value)}>
          <option value="">Select a lifecycle state…</option>
          {allowed.map((s) => <option key={s} value={s}>{human(s)}</option>)}
        </select>
        {to === "pending_return" && <p className="mt-1 text-[11.5px] text-warn">Pending return requires a return record. Create one from the spare-parts workflow or the return queue.</p>}
      </div>
      {to === "stored" && (
        <div>
          <label className="label" htmlFor="tr-loc">Storage location (required)</label>
          <input id="tr-loc" className="input" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Spares cage A / Bin 03" maxLength={120} />
        </div>
      )}
      {to === "installed" && (
        <div>
          <label className="label" htmlFor="tr-dev">Installed in device (required)</label>
          <select id="tr-dev" className="input" value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
            <option value="">Select a device…</option>
            {devices.map((d) => <option key={d.id} value={d.id}>{d.display_id} ({d.model})</option>)}
          </select>
        </div>
      )}
      {(to === "quarantined" || to === "decommissioned" || to === "in_repair" || to === "returned") && (
        <div>
          <label className="label" htmlFor="tr-note">{to === "quarantined" || to === "decommissioned" ? "Reason (required)" : "Note"}</label>
          <textarea id="tr-note" className="input" rows={2} value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} />
        </div>
      )}
      <button className="btn-primary" disabled={!to || act.isPending}><ArrowRightLeft className="h-4 w-4" aria-hidden />Record transition</button>
    </form>
  );
}

export function AssetDetail() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const q = useAsset(id);
  const auditRef = useRef<HTMLDivElement>(null);
  const tab = params.get("tab");

  useEffect(() => {
    if (tab === "audit" && q.data && !q.data.device_id && auditRef.current) {
      auditRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
      auditRef.current.focus({ preventScroll: true });
    }
  }, [tab, q.data]);

  if (q.isLoading) return <LoadingBlock rows={10} label="Loading asset" />;
  if (q.error || !q.data) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const a = q.data;

  return (
    <div className="space-y-5">
      <PageHeader eyebrow={`Asset · ${human(a.asset_type)}`}
        title={<span className="flex flex-wrap items-center gap-2"><span className="mono">{a.display_id}</span><LifecycleBadge status={a.status} />
          {a.origin === "simulation" && <Pill className="border-sim/25 bg-sim-50 text-sim">created by simulation</Pill>}</span>}
        actions={<button className="btn-secondary no-print" onClick={() => window.print()}><Printer className="h-4 w-4" aria-hidden />Print label</button>}>
        {a.model} · serial <span className="mono">{a.serial_number}</span>
      </PageHeader>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }} className="min-w-0 space-y-5">
          {a.device_id ? (
            <Panel title={<span className="mono">{a.device}</span>} sub="Racked device: hardware, cabling, power, incidents, acceptance, lifecycle and audit">
              <DevicePanel id={a.device} initialTab={tab ?? "overview"} />
            </Panel>
          ) : (
            <div ref={auditRef} tabIndex={-1} className="scroll-mt-20 outline-none">
              <Panel title="Audit trail" icon={<History className="h-4 w-4" />} sub="Every material change to this asset, oldest first">
                <AuditList items={a.audit} />
              </Panel>
            </div>
          )}
          {a.device_id && a.audit?.length > 0 && (
            <Panel title="Asset audit trail" icon={<History className="h-4 w-4" />} sub="Lifecycle changes recorded against the asset record">
              <AuditList items={a.audit} />
            </Panel>
          )}
        </motion.div>

        <div className="space-y-5">
          <Panel title="Asset record">
            <dl className="divide-y divide-line-soft">
              <KV k="Asset tag" v={a.display_id} mono />
              <KV k="Serial" v={a.serial_number} mono />
              <KV k="Type" v={human(a.asset_type)} />
              <KV k="Manufacturer" v={a.manufacturer} />
              <KV k="Model / part" v={a.part_number ?? a.model} mono />
              <KV k="Lifecycle" v={<LifecycleBadge status={a.status} />} />
              <KV k="Location" v={a.location || "—"} />
              <KV k="Installed in" v={a.installed_in ? <Link className="mono text-accent-700 hover:underline" to={`/infrastructure?device=${a.installed_in.display_id}`}>{a.installed_in.display_id}</Link> : "—"} />
              <KV k="Warranty" v={<span className={a.warranty_status === "unknown" ? "text-warn" : ""}>{warranty(a.warranty_status)}</span>} />
              {a.warranty_end && <KV k="Warranty end" v={fmtDateTime(a.warranty_end)} mono />}
            </dl>
            {a.notes && <p className="mt-2 text-[12px] text-ink-2">{a.notes}</p>}
          </Panel>

          {a.return_record && (
            <Panel title="Return record" icon={<Undo2 className="h-4 w-4" />}>
              <div className="flex flex-wrap items-center gap-2 text-[13px]">
                <span className="mono font-semibold">{a.return_record.display_id}</span>
                <Pill className="border-line bg-canvas text-ink-2">{human(a.return_record.shipping_status)}</Pill>
              </div>
              <p className="mt-1 text-[12.5px] text-ink-2">{a.return_record.failure_summary}</p>
              <Link to="/returns" className="btn-ghost btn-sm mt-2">Open return queue →</Link>
            </Panel>
          )}

          <Panel title="Lifecycle transition" icon={<ArrowRightLeft className="h-4 w-4" />} sub="Validated against allowed transitions and required information">
            <TransitionForm asset={a} />
          </Panel>

          <Panel title="Label">
            <QrLabel title={a.display_id} subtitle={a.serial_number} path={`/assets/${a.id}`} />
            <p className="mt-2 text-[11.5px] text-ink-2">The QR code opens this asset's local route.</p>
          </Panel>
        </div>
      </div>
    </div>
  );
}
