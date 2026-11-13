import clsx from "clsx";
import { motion } from "framer-motion";
import { AlertTriangle, Check, CircleCheck, CircleX, PackageCheck, PackageOpen, PackagePlus, ScrollText, Undo2, Wrench } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { post } from "@/api/client";
import { useAction, useAssets, useDevice, useReservations, useReturns, useSpares, useTxns } from "@/api/hooks";
import type { Reservation, Stock } from "@/api/types";
import { Pill } from "@/components/ui/Badges";
import { Empty, ErrorState, LoadingBlock, Modal, PageHeader, Panel } from "@/components/ui/Primitives";
import { fmtDateTime, human, relative } from "@/lib/format";

const DEMO_SERIAL = "SIM-PSU-SP-0103";
const DEMO_FAILURE = "PSU2 Status.Health=Critical, no output; SEL 'Failure detected'.";

const newKey = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);

function ResStatus({ s }: { s: string }) {
  const cls = s === "active" ? "border-accent/30 bg-accent-50 text-accent-700" : s === "consumed" ? "border-ok/30 bg-ok-50 text-ok" : "border-line-strong bg-canvas text-ink-2";
  return <Pill className={cls}>{s}</Pill>;
}

function Stepper({ steps }: { steps: { label: string; done: boolean }[] }) {
  const current = steps.findIndex((s) => !s.done);
  return (
    <ol className="grid grid-cols-1 gap-2 sm:grid-cols-4" aria-label="Repair workflow progress">
      {steps.map((s, i) => {
        const cur = i === current;
        return (
          <motion.li key={s.label} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05, duration: 0.2 }}
            className={clsx("relative flex items-center gap-2.5 rounded-xl border p-2.5 transition-colors duration-200",
              s.done ? "border-ok/30 bg-ok-50/60" : cur ? "border-accent/40 bg-accent-50/60 shadow-focus" : "border-line bg-white")}
            aria-current={cur ? "step" : undefined}>
            <motion.span initial={false} animate={{ scale: cur ? 1.08 : 1 }}
              className={clsx("grid h-6 w-6 shrink-0 place-items-center rounded-full border-2 text-[10px] font-bold",
                s.done ? "border-ok bg-ok text-white" : cur ? "border-accent bg-white text-accent" : "border-line-strong text-ink-3")}>
              {s.done ? <Check className="h-3.5 w-3.5" aria-hidden /> : i + 1}
            </motion.span>
            <span className={clsx("text-[12.5px] font-medium", s.done ? "text-ink" : cur ? "text-accent-700" : "text-ink-2")}>{s.label}</span>
            <span className="sr-only">{s.done ? "(done)" : cur ? "(current)" : "(pending)"}</span>
          </motion.li>
        );
      })}
    </ol>
  );
}

export function Spares() {
  const [params, setParams] = useSearchParams();
  const deviceId = params.get("device") ? Number(params.get("device")) : null;
  const incidentId = params.get("incident") ? Number(params.get("incident")) : null;
  const lowOnly = params.get("low") === "1";

  const spares = useSpares(deviceId);
  const reservations = useReservations();
  const returns = useReturns();
  const txns = useTxns();
  const device = useDevice(deviceId);
  const quarantined = useAssets("status=quarantined");

  const [reserveFor, setReserveFor] = useState<Stock | null>(null);
  const [consumeFor, setConsumeFor] = useState<Reservation | null>(null);
  const [receiveFor, setReceiveFor] = useState<Stock | null>(null);
  const [releaseFor, setReleaseFor] = useState<Reservation | null>(null);
  const [returnOpen, setReturnOpen] = useState(false);
  const [lastConsume, setLastConsume] = useState<any>(null);

  // Mark "Identify compatible spare" reviewed in the guided demo (no-op if no demo is running).
  const viewed = useRef(false);
  useEffect(() => {
    if (deviceId && incidentId && !viewed.current) {
      viewed.current = true;
      post("/demos/replace-component/view/spare").catch(() => undefined);
    }
  }, [deviceId, incidentId]);

  const incRes = (reservations.data ?? []).filter((r) => incidentId && r.incident_id === incidentId);
  const incReturn = (returns.data ?? []).find((r) => incidentId && r.incident_id === incidentId);
  const workflow = deviceId && incidentId;
  const steps = [
    { label: "Identify compatible spare", done: true },
    { label: "Reserve", done: incRes.some((r) => r.status === "active" || r.status === "consumed") },
    { label: "Record replacement & consume", done: incRes.some((r) => r.status === "consumed") },
    { label: "Return failed part", done: !!incReturn },
  ];
  const activeRes = incRes.find((r) => r.status === "active");
  const needsReturn = steps[2].done && !incReturn;

  const stock = (spares.data?.stock ?? []).filter((s) => !lowOnly || s.low_stock);

  return (
    <div className="space-y-5">
      <PageHeader title="Spare parts"
        actions={<button className="btn-secondary" aria-pressed={lowOnly} onClick={() => setParams((p) => { lowOnly ? p.delete("low") : p.set("low", "1"); return p; })}>
          {lowOnly ? "Show all stock" : "Low stock only"}</button>}>
        Stock, reservations and the inventory ledger.
      </PageHeader>

      {workflow && (
        <Panel title="Repair workflow" icon={<Wrench className="h-4 w-4" />}
          sub={<>Device <span className="mono">{device.data?.display_id ?? deviceId}</span> · incident <Link className="mono text-accent-700 hover:underline" to={`/incidents/${incidentId}`}>#{incidentId}</Link></>}>
          <Stepper steps={steps} />
          <div className="mt-3 flex flex-wrap items-center gap-2 text-[12.5px]">
            {!steps[1].done && <span className="text-ink-2">Reserve a part marked <b>Compatible</b> in the table below.</span>}
            {activeRes && (
              <button className="btn-primary" onClick={() => setConsumeFor(activeRes)}><PackageCheck className="h-4 w-4" aria-hidden />Record replacement &amp; consume {activeRes.display_id}</button>
            )}
            {needsReturn && <button className="btn-primary" onClick={() => setReturnOpen(true)}><Undo2 className="h-4 w-4" aria-hidden />Move failed part to return queue</button>}
            {incReturn && (
              <span className="flex items-center gap-1.5 text-ok"><CircleCheck className="h-4 w-4" aria-hidden />Return {incReturn.display_id} recorded. <Link to="/returns" className="text-accent-700 hover:underline">Open queue</Link> · <Link to={`/incidents/${incidentId}`} className="text-accent-700 hover:underline">Re-run health check on the incident</Link></span>
            )}
          </div>
          <p className="mt-2 text-[11.5px] text-ink-2">Workflow completion records the logistics. The physical PSU swap itself is simulated in this lab.</p>
        </Panel>
      )}

      <Panel title={spares.data?.device ? <>Stock compatible with <span className="mono">{spares.data.device.display_id}</span> ({spares.data.device.model})</> : "Spare stock"}
        icon={<PackageOpen className="h-4 w-4" />} bodyClass="">
        {spares.isLoading ? <LoadingBlock rows={6} /> : spares.error ? <div className="p-4"><ErrorState error={spares.error} retry={() => spares.refetch()} /></div> : !stock.length ? (
          <Empty title={lowOnly ? "No part types are below their reorder threshold" : "No stock recorded"} />
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <caption className="sr-only">Spare stock by part type and location</caption>
              <thead><tr>
                <th scope="col">Part</th><th scope="col">Location</th>
                {deviceId && <th scope="col">Compatibility</th>}
                <th scope="col" className="text-right">On hand</th><th scope="col" className="text-right">Reserved</th><th scope="col" className="text-right">Available</th>
                <th scope="col" className="text-right">Reorder at</th><th scope="col">Stock</th><th scope="col"><span className="sr-only">Actions</span></th>
              </tr></thead>
              <tbody>
                {stock.map((s, i) => (
                  <motion.tr key={s.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: Math.min(i * 0.03, 0.2) }}
                    className={clsx(deviceId && s.compatible === false && "bg-crit-50/30")}>
                    <td className="min-w-[200px]"><div className="mono font-semibold">{s.part_number}</div><div className="text-[12px] text-ink-2">{s.part_name}</div></td>
                    <td className="min-w-[170px]"><div className="text-[12.5px]">{s.location}</div><div className="text-[11.5px] capitalize text-ink-3">{s.category}</div></td>
                    {deviceId && <td>{s.compatible ? <Pill className="border-ok/30 bg-ok-50 text-ok"><CircleCheck className="h-3 w-3" aria-hidden />Compatible</Pill>
                      : <Pill className="border-crit/30 bg-crit-50 text-crit" title={`Listed for: ${s.compatible_models.join(", ")}`}><CircleX className="h-3 w-3" aria-hidden />Not compatible</Pill>}</td>}
                    <td className="mono text-right">{s.on_hand}</td>
                    <td className="mono text-right">{s.reserved}</td>
                    <td className="mono text-right font-semibold">{s.available}</td>
                    <td className="mono text-right text-ink-2">{s.reorder_threshold}</td>
                    <td>{s.low_stock ? <Pill className="border-warn/30 bg-warn-50 text-warn"><AlertTriangle className="h-3 w-3" aria-hidden />Low stock</Pill> : <span className="text-[12px] text-ink-2">OK</span>}</td>
                    <td className="whitespace-nowrap text-right">
                      <button className="btn-secondary btn-sm" disabled={s.available < 1} onClick={() => setReserveFor(s)} aria-label={`Reserve ${s.part_number}`}>Reserve</button>
                      <button className="btn-ghost btn-sm ml-1" onClick={() => setReceiveFor(s)} aria-label={`Receive stock for ${s.part_number}`} title="Receive stock"><PackagePlus className="h-3.5 w-3.5" aria-hidden /><span className="hidden 2xl:inline">Receive</span></button>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="border-t border-line-soft px-4 py-2.5 text-[11.5px] text-ink-2">On hand = SUM(ledger quantity deltas). Available = on hand − active reservations. Negative stock, over-reservation and double consumption are rejected by the backend.</p>
      </Panel>

      <Panel title={`Reservations${reservations.data ? ` · ${reservations.data.length}` : ""}`} icon={<PackageCheck className="h-4 w-4" />} bodyClass="">
        {reservations.isLoading ? <LoadingBlock /> : !reservations.data?.length ? <Empty title="No reservations">Reserve a spare against a device or incident to hold it.</Empty> : (
          <div className="overflow-x-auto">
            <table className="table">
              <caption className="sr-only">Spare part reservations</caption>
              <thead><tr><th scope="col">Reservation</th><th scope="col">Part</th><th scope="col" className="text-right">Qty</th><th scope="col">Status</th><th scope="col">Device</th>
                <th scope="col">Incident</th><th scope="col">Reason</th><th scope="col">Created</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {reservations.data.map((r) => (
                  <tr key={r.id}>
                    <td className="mono font-medium">{r.display_id}{r.origin === "simulation" && <div className="text-[10.5px] text-sim">simulation</div>}</td>
                    <td className="mono">{r.part_number}</td>
                    <td className="mono text-right">{r.quantity}</td>
                    <td><ResStatus s={r.status} />{r.compatibility_exception && <div className="mt-0.5"><Pill className="border-warn/30 bg-warn-50 text-warn" title={`${r.exception_reviewed_by}: ${r.exception_note}`}>Reviewed exception</Pill></div>}</td>
                    <td>{r.device ? <Link className="mono text-accent-700 hover:underline" to={`/infrastructure?device=${r.device.display_id}`}>{r.device.display_id}</Link> : "—"}</td>
                    <td>{r.incident_id ? <Link className="mono text-accent-700 hover:underline" to={`/incidents/${r.incident_id}`}>#{r.incident_id}</Link> : "—"}</td>
                    <td className="max-w-[220px] truncate text-ink-2" title={r.reason}>{r.reason || "—"}</td>
                    <td className="mono whitespace-nowrap text-ink-2">{relative(r.created_at)}</td>
                    <td className="whitespace-nowrap text-right">
                      {r.status === "active" && <>
                        <button className="btn-secondary btn-sm" onClick={() => setConsumeFor(r)}>Consume</button>
                        <button className="btn-ghost btn-sm ml-1" onClick={() => setReleaseFor(r)}>Release</button>
                      </>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Inventory ledger" icon={<ScrollText className="h-4 w-4" />} sub="Immutable transactions, newest first" bodyClass="">
        {txns.isLoading ? <LoadingBlock /> : !txns.data?.length ? <Empty title="No transactions" /> : (
          <div className="max-h-[420px] overflow-auto">
            <table className="table">
              <caption className="sr-only">Inventory ledger</caption>
              <thead><tr><th scope="col">Txn</th><th scope="col">When (UTC)</th><th scope="col">Stock</th><th scope="col">Part</th><th scope="col">Kind</th>
                <th scope="col" className="text-right">Δ Qty</th><th scope="col">Reservation</th><th scope="col">Note</th><th scope="col">Actor</th></tr></thead>
              <tbody>
                {txns.data.map((t) => (
                  <tr key={t.id}>
                    <td className="mono">{t.display_id}</td>
                    <td className="mono whitespace-nowrap text-ink-2">{fmtDateTime(t.occurred_at)}</td>
                    <td className="mono text-ink-2">{t.stock}</td>
                    <td className="mono">{t.part_number}</td>
                    <td>{t.kind}{t.origin === "simulation" && <span className="ml-1 text-[10.5px] text-sim">sim</span>}</td>
                    <td className={clsx("mono text-right font-semibold", t.quantity_delta < 0 ? "text-crit" : "text-ok")}>
                      {t.quantity_delta > 0 ? "+" : "−"}{Math.abs(t.quantity_delta)}<span className="sr-only">{t.quantity_delta < 0 ? " removed" : " added"}</span>
                    </td>
                    <td className="mono text-ink-2">{t.reservation_id ? `#${t.reservation_id}` : "—"}</td>
                    <td className="max-w-[240px] truncate text-ink-2" title={t.note}>{t.note || "—"}</td>
                    <td>{t.actor}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <ReserveDialog stock={reserveFor} onClose={() => setReserveFor(null)} deviceId={deviceId} incidentId={incidentId} deviceName={spares.data?.device?.display_id} />
      <ConsumeDialog res={consumeFor} onClose={() => setConsumeFor(null)} deviceId={consumeFor?.device?.id ?? deviceId} incidentId={incidentId}
        onDone={(r) => { setLastConsume(r); if (incidentId) setReturnOpen(true); }} />
      <ReceiveDialog stock={receiveFor} onClose={() => setReceiveFor(null)} />
      <ReleaseDialog res={releaseFor} onClose={() => setReleaseFor(null)} />
      <ReturnDialog open={returnOpen} onClose={() => setReturnOpen(false)} incidentId={incidentId} deviceId={deviceId}
        failedAsset={lastConsume?.failed_asset ?? null} replacementAssetId={lastConsume?.replacement_asset?.id ?? null}
        candidates={quarantined.data ?? []} />
    </div>
  );
}

function ReserveDialog({ stock, onClose, deviceId, incidentId, deviceName }: { stock: Stock | null; onClose: () => void; deviceId: number | null; incidentId: number | null; deviceName?: string }) {
  const [qty, setQty] = useState(1);
  const [reason, setReason] = useState("");
  const [exc, setExc] = useState(false);
  const [reviewer, setReviewer] = useState("");
  const [note, setNote] = useState("");
  const key = useMemo(() => newKey(), [stock?.id]); // one key per dialog → double-submit is idempotent
  useEffect(() => {
    if (stock) { setQty(1); setReason(incidentId ? `Replace failed component (incident #${incidentId})` : ""); setExc(false); setReviewer(""); setNote(""); }
  }, [stock, incidentId]);
  const incompatible = !!deviceId && stock?.compatible === false;
  const act = useAction(() => post("/reservations", {
    stock_id: stock!.id, quantity: qty, device_id: deviceId, incident_id: incidentId, reason,
    compatibility_exception: incompatible && exc, exception_reviewed_by: reviewer, exception_note: note,
  }, { idempotent: key }), { success: (r: any) => `Reserved ${r.quantity} × ${r.part_number} (${r.display_id})`, onSuccess: onClose });
  return (
    <Modal open={!!stock} onOpenChange={(o) => !o && onClose()} title={`Reserve ${stock?.part_number ?? ""}`}
      description={deviceName ? `For ${deviceName}. Available ${stock?.available}. A reservation holds stock; it does not consume it.` : `Available ${stock?.available}. A reservation holds stock; it does not consume it.`}>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); act.mutate(); }}>
        {incompatible && (
          <div className="rounded-lg border border-crit/30 bg-crit-50/60 p-3 text-[12.5px]" role="alert">
            <div className="flex items-center gap-1.5 font-semibold text-crit"><CircleX className="h-4 w-4" aria-hidden />Not listed as compatible with this device</div>
            <p className="mt-1 text-ink-2">Listed for: <span className="mono">{stock?.compatible_models.join(", ")}</span>. Reserve a compatible part, or record a reviewed exception.</p>
          </div>
        )}
        <div className="grid grid-cols-[100px_1fr] gap-3">
          <div><label className="label" htmlFor="rs-qty">Quantity</label>
            <input id="rs-qty" type="number" min={1} max={stock?.available ?? 1} className="input" value={qty} onChange={(e) => setQty(Math.max(1, Number(e.target.value) || 1))} /></div>
          <div><label className="label" htmlFor="rs-reason">Reason</label>
            <input id="rs-reason" className="input" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={2000} /></div>
        </div>
        {incompatible && (
          <fieldset className="space-y-2 rounded-lg border border-line p-3">
            <legend className="px-1 text-[12px] font-medium">Compatibility exception</legend>
            <label className="flex items-center gap-2 text-[12.5px]"><input type="checkbox" checked={exc} onChange={(e) => setExc(e.target.checked)} />Reviewed compatibility exception</label>
            {exc && <>
              <div><label className="label" htmlFor="rs-rev">Reviewed by</label><input id="rs-rev" className="input" value={reviewer} onChange={(e) => setReviewer(e.target.value)} maxLength={80} /></div>
              <div><label className="label" htmlFor="rs-note">Justification</label><textarea id="rs-note" className="input" rows={2} value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} /></div>
            </>}
          </fieldset>
        )}
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={act.isPending || (incompatible && (!exc || !reviewer.trim() || !note.trim()))}>Reserve</button>
        </div>
      </form>
    </Modal>
  );
}

function ConsumeDialog({ res, onClose, deviceId, incidentId, onDone }: { res: Reservation | null; onClose: () => void; deviceId: number | null; incidentId: number | null; onDone: (r: any) => void }) {
  const dev = useDevice(res && deviceId ? deviceId : null);
  const inputs = dev.data?.power.inputs ?? [];
  const isDemoPsu = res?.part_number === "NL-PSU-800P" && !!(incidentId || res?.incident_id);
  const [serial, setSerial] = useState("");
  const [pi, setPi] = useState<string>("");
  const [note, setNote] = useState("");
  const key = useMemo(() => newKey(), [res?.id]);
  useEffect(() => {
    if (res) { setSerial(isDemoPsu ? DEMO_SERIAL : ""); setNote(isDemoPsu ? "Hot-swap PSU2 (simulated physical work)" : ""); }
  }, [res, isDemoPsu]);
  useEffect(() => {
    if (res && res.part_number.includes("PSU")) {
      const psu2 = inputs.find((x) => x.input === "PSU2");
      setPi(psu2 ? String(psu2.input_id) : "");
    } else setPi("");
  }, [res, inputs.length]); // eslint-disable-line react-hooks/exhaustive-deps
  const act = useAction(() => post<any>(`/reservations/${res!.id}/consume`, {
    replacement_serial: serial.trim(), power_input_id: pi ? Number(pi) : null, note,
  }, { idempotent: key }), {
    success: (r) => `Consumed ${r.reservation.display_id}; ${r.replacement_asset.display_id} recorded as installed`,
    onSuccess: (r) => { onClose(); onDone(r); },
  });
  return (
    <Modal open={!!res} onOpenChange={(o) => !o && onClose()} title={`Record replacement · consume ${res?.display_id ?? ""}`} description={`${res?.part_number ?? ""} · ${res?.part_name ?? ""}`}>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); act.mutate(); }}>
        <div className="rounded-lg bg-canvas p-3 text-[12px] text-ink-2">
          <div className="mb-1 flex items-center gap-1.5"><Pill className="border-sim/25 bg-sim-50 text-sim">Physical work is simulated</Pill></div>
          One atomic transaction: ledger −{res?.quantity ?? 1}, reservation marked consumed, the new part recorded as an installed asset, the failed part quarantined,
          and the repair recorded on the linked incident. If any step fails, nothing is written.
        </div>
        <div>
          <label className="label" htmlFor="cs-serial">Replacement serial number{isDemoPsu ? " (simulated demo serial)" : ""}</label>
          <input id="cs-serial" className="input mono" value={serial} onChange={(e) => setSerial(e.target.value)} maxLength={64} required />
        </div>
        {inputs.length > 0 && res?.part_number.includes("PSU") && (
          <div>
            <label className="label" htmlFor="cs-pi">Installed in power input</label>
            <select id="cs-pi" className="input" value={pi} onChange={(e) => setPi(e.target.value)}>
              <option value="">Not a power-input component</option>
              {inputs.map((x) => <option key={x.input_id} value={x.input_id}>{x.input}{x.component_asset ? ` (currently ${x.component_asset})` : ""}</option>)}
            </select>
          </div>
        )}
        <div><label className="label" htmlFor="cs-note">Note</label><input id="cs-note" className="input" value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} /></div>
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={act.isPending || serial.trim().length < 3}>Consume reservation</button>
        </div>
      </form>
    </Modal>
  );
}

function ReturnDialog({ open, onClose, incidentId, deviceId, failedAsset, replacementAssetId, candidates }: {
  open: boolean; onClose: () => void; incidentId: number | null; deviceId: number | null; failedAsset: any; replacementAssetId: number | null; candidates: any[];
}) {
  const [assetId, setAssetId] = useState<string>("");
  const [summary, setSummary] = useState("");
  useEffect(() => {
    if (open) {
      setAssetId(failedAsset ? String(failedAsset.id) : candidates[0] ? String(candidates[0].id) : "");
      setSummary(incidentId ? DEMO_FAILURE : "");
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const act = useAction(() => post<any>("/returns", {
    failed_asset_id: Number(assetId), failure_summary: summary, incident_id: incidentId, replacement_asset_id: replacementAssetId, original_device_id: deviceId,
  }), { success: (r) => `Return ${r.display_id} recorded. No vendor was contacted.`, onSuccess: onClose });
  const options = failedAsset ? [failedAsset, ...candidates.filter((c) => c.id !== failedAsset.id)] : candidates;
  return (
    <Modal open={open} onOpenChange={(o) => !o && onClose()} title="Move failed part to return queue" description="Records the return. It does not contact a vendor.">
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); act.mutate(); }}>
        <div>
          <label className="label" htmlFor="rt-asset">Failed component</label>
          {options.length === 0 ? <p className="text-[12.5px] text-ink-2">No quarantined assets found. Consume the reservation first, which quarantines the failed part.</p> : (
            <select id="rt-asset" className="input" value={assetId} onChange={(e) => setAssetId(e.target.value)}>
              {options.map((a) => <option key={a.id} value={a.id}>{a.display_id} · {a.serial_number} ({human(a.status)})</option>)}
            </select>
          )}
        </div>
        <div><label className="label" htmlFor="rt-sum">Failure summary</label>
          <textarea id="rt-sum" className="input" rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} maxLength={4000} /></div>
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" className="btn-secondary" onClick={onClose}>Not now</button>
          <button className="btn-primary" disabled={act.isPending || !assetId || summary.trim().length < 3}>Create return record</button>
        </div>
      </form>
    </Modal>
  );
}

function ReceiveDialog({ stock, onClose }: { stock: Stock | null; onClose: () => void }) {
  const [qty, setQty] = useState(1);
  const [note, setNote] = useState("");
  useEffect(() => { if (stock) { setQty(1); setNote(""); } }, [stock]);
  const act = useAction(() => post(`/spares/${stock!.id}/receive`, { quantity: qty, note }), { success: `Received ${qty} × ${stock?.part_number ?? ""}`, onSuccess: onClose });
  return (
    <Modal open={!!stock} onOpenChange={(o) => !o && onClose()} title={`Receive ${stock?.part_number ?? ""}`} description={`Adds a receive transaction to the ledger at ${stock?.location ?? ""}.`}>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); act.mutate(); }}>
        <div className="grid grid-cols-[100px_1fr] gap-3">
          <div><label className="label" htmlFor="rc-qty">Quantity</label><input id="rc-qty" type="number" min={1} max={1000} className="input" value={qty} onChange={(e) => setQty(Math.max(1, Number(e.target.value) || 1))} /></div>
          <div><label className="label" htmlFor="rc-note">Note (e.g. delivery reference)</label><input id="rc-note" className="input" value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} /></div>
        </div>
        <div className="flex justify-end gap-2"><button type="button" className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={act.isPending}>Receive</button></div>
      </form>
    </Modal>
  );
}

function ReleaseDialog({ res, onClose }: { res: Reservation | null; onClose: () => void }) {
  const [note, setNote] = useState("");
  useEffect(() => { if (res) setNote(""); }, [res]);
  const act = useAction(() => post(`/reservations/${res!.id}/release`, { note }), { success: `Released ${res?.display_id ?? ""}`, onSuccess: onClose });
  return (
    <Modal open={!!res} onOpenChange={(o) => !o && onClose()} title={`Release ${res?.display_id ?? ""}`} description="Returns the held quantity to available stock. Nothing is consumed.">
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); act.mutate(); }}>
        <div><label className="label" htmlFor="rl-note">Reason</label><input id="rl-note" className="input" value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} /></div>
        <div className="flex justify-end gap-2"><button type="button" className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={act.isPending}>Release reservation</button></div>
      </form>
    </Modal>
  );
}
