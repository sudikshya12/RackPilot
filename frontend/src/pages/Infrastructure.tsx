import * as Tabs from "@radix-ui/react-tabs";
import clsx from "clsx";
import { motion } from "framer-motion";
import { Cable as CableIcon, MoveVertical, Plus, Printer, Route, ShieldAlert, Tag, Zap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, post } from "@/api/client";
import { useAction, useCableAudit, useCables, useDevice, usePower, useRacks } from "@/api/hooks";
import type { Cable, TraceHop } from "@/api/types";
import { CableTrace } from "@/components/rack/CableTrace";
import { DeviceDrawer } from "@/components/rack/DevicePanel";
import { QrLabel } from "@/components/rack/QrLabel";
import { RackElevation, RackTable } from "@/components/rack/RackElevation";
import { ModeledBadge, Pill } from "@/components/ui/Badges";
import { Empty, ErrorState, Field, LoadingBlock, Modal, PageHeader, Panel } from "@/components/ui/Primitives";

type Trace = { hops: TraceHop[]; text: string; complete: boolean; note: string; basis: string };

function PlaceDevice() {
  const racks = useRacks();
  const [dev, setDev] = useState("");
  const [rack, setRack] = useState("NL-R01");
  const [u, setU] = useState(10);
  const place = useAction(() => post(`/devices/${dev}/place`, { rack, position_u: u }), { success: "Device placed. Audit event recorded." });
  const devices = (racks.data ?? []).flatMap((r) => r.devices).filter((d) => d.u_height > 0);
  return (
    <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); place.mutate(); }}>
      <Field label="Device" htmlFor="pl-dev"><select id="pl-dev" className="input h-8 w-40" value={dev} onChange={(e) => setDev(e.target.value)}><option value="">Select…</option>{devices.map((d) => <option key={d.display_id} value={d.display_id}>{d.display_id} ({d.u_height}U)</option>)}</select></Field>
      <Field label="Rack" htmlFor="pl-rack"><select id="pl-rack" className="input h-8 w-28" value={rack} onChange={(e) => setRack(e.target.value)}>{racks.data?.map((r) => <option key={r.id}>{r.display_id}</option>)}</select></Field>
      <Field label="Lowest U" htmlFor="pl-u"><input id="pl-u" type="number" className="input h-8 w-20" value={u} onChange={(e) => setU(Number(e.target.value))} /></Field>
      <button className="btn-secondary h-8" disabled={!dev || place.isPending}><MoveVertical className="h-3.5 w-3.5" aria-hidden />Move</button>
      <p className="w-full text-[11.5px] text-ink-2">The server rejects overlapping and out-of-bounds placements. Try moving lab-srv-01 to U31 to see the validation.</p>
    </form>
  );
}

function RecordCable({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const racks = useRacks();
  const devices = (racks.data ?? []).flatMap((r) => r.devices).filter((d) => d.role !== "pdu");
  const [a, setA] = useState("lab-sw-01");
  const [b, setB] = useState("lab-sw-02");
  const da = useDevice(a);
  const db = useDevice(b);
  const [ai, setAi] = useState<number | "">("");
  const [bi, setBi] = useState<number | "">("");
  const [type, setType] = useState("om4-lc-lc");
  const [label, setLabel] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const create = useAction(() => post<any>("/cables", { a_interface_id: ai, b_interface_id: bi, cable_type: type, label: label || null, intended_speed_mbps: 10000 }), {
    onSuccess: (r) => setResult(r.warnings?.length ? `Recorded with warning: ${r.warnings.map((w: any) => w.message).join(" ")}` : `Recorded ${r.label}.`),
  });
  const free = (d: typeof da.data) => (d?.interfaces ?? []).map((i) => ({ ...i, used: d!.cables.some((c) => c.a.interface_id === i.id || c.b.interface_id === i.id) }));
  return (
    <Modal open={open} onOpenChange={(o) => { onOpenChange(o); setResult(null); }} title="Record a cable" description="Both endpoints must be modeled interfaces. Occupied ports, incompatible connectors and missing endpoints are rejected by the server." wide>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {([["A", a, setA, ai, setAi, da.data], ["B", b, setB, bi, setBi, db.data]] as const).map(([side, dv, setDv, iv, setIv, data]) => (
            <fieldset key={side} className="space-y-2 rounded-xl border border-line p-3">
              <legend className="px-1 text-[12px] font-semibold">Endpoint {side}</legend>
              <select aria-label={`Endpoint ${side} device`} className="input h-8" value={dv} onChange={(e) => { setDv(e.target.value); setIv(""); }}>{devices.map((d) => <option key={d.display_id}>{d.display_id}</option>)}</select>
              <select aria-label={`Endpoint ${side} interface`} className="input h-8" value={iv} onChange={(e) => setIv(e.target.value ? Number(e.target.value) : "")}>
                <option value="">Interface…</option>
                {free(data).map((i) => <option key={i.id} value={i.id}>{i.name} · {i.connector}{i.used ? " (in use)" : ""}</option>)}
              </select>
            </fieldset>
          ))}
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Cable type" htmlFor="cb-type"><select id="cb-type" className="input" value={type} onChange={(e) => setType(e.target.value)}>{["om4-lc-lc", "os2-lc-lc", "dac-sfp+", "cat6a", "cat6"].map((t) => <option key={t}>{t}</option>)}</select></Field>
          <Field label="Label (blank = unlabeled, flagged)" htmlFor="cb-label"><input id="cb-label" className="input font-mono" value={label} onChange={(e) => setLabel(e.target.value.toUpperCase())} placeholder="CBL-0110" /></Field>
        </div>
        {result && <p className="rounded-lg bg-ok-50 px-3 py-2 text-[12.5px] text-ok" role="status">{result}</p>}
        <div className="flex justify-end gap-2"><button type="button" className="btn-secondary" onClick={() => onOpenChange(false)}>Close</button><button className="btn-primary" disabled={!ai || !bi || create.isPending}>Validate & record</button></div>
      </form>
    </Modal>
  );
}

export function Infrastructure() {
  const [params, setParams] = useSearchParams();
  const racks = useRacks();
  const cables = useCables();
  const audit = useCableAudit();
  const power = usePower();
  const [face, setFace] = useState<"front" | "rear">("front");
  const [text, setText] = useState(false);
  const [trace, setTrace] = useState<{ cable: number; t: Trace } | null>(null);
  const [recordOpen, setRecordOpen] = useState(false);
  const [labelFor, setLabelFor] = useState<Cable | null>(null);
  const [newLabel, setNewLabel] = useState("");
  const tab = params.get("tab") ?? (params.get("cable") ? "cables" : "racks");
  const selected = params.get("device");
  const doLabel = useAction(() => post(`/cables/${labelFor!.id}/label`, { label: newLabel }), { success: "Cable labeled", onSuccess: () => setLabelFor(null) });

  const runTrace = async (c: Cable) => setTrace({ cable: c.id, t: await api<Trace>(`/interfaces/${c.a.interface_id}/trace`) });
  useEffect(() => {
    const cid = Number(params.get("cable"));
    const c = cables.data?.find((x) => x.id === cid);
    if (c && trace?.cable !== cid) runTrace(c);
  }, [params, cables.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const issuesByCable = useMemo(() => {
    const m = new Map<number, any[]>();
    (audit.data?.issues ?? []).forEach((i) => m.set(i.cable_id, [...(m.get(i.cable_id) ?? []), i]));
    return m;
  }, [audit.data]);

  return (
    <div className="space-y-5">
      <PageHeader title="Infrastructure" actions={<ModeledBadge />}>Racks, cabling and power for North Lab.</PageHeader>
      <Tabs.Root value={tab} onValueChange={(v) => setParams((p) => { p.set("tab", v); return p; })}>
        <Tabs.List className="mb-4 flex gap-1 overflow-x-auto rounded-xl border border-line bg-white p-1" aria-label="Infrastructure views">
          {[["racks", "Rack elevations"], ["cables", `Cables${cables.data ? ` · ${cables.data.length}` : ""}`], ["power", "Power topology"], ["labels", "Labels"]].map(([v, l]) => (
            <Tabs.Trigger key={v} value={v} className="relative whitespace-nowrap rounded-lg px-3 py-1.5 text-[13px] font-medium text-ink-2 transition-colors hover:text-ink data-[state=active]:text-white">
              {tab === v && <motion.span layoutId="infra-tab" className="absolute inset-0 rounded-lg bg-nav" transition={{ duration: 0.2 }} />}
              <span className="relative">{l}</span>
              {v === "cables" && (audit.data?.issues.length ?? 0) > 0 && <span className="relative ml-1.5 rounded-full bg-warn px-1.5 text-[10px] font-bold text-white">{audit.data!.issues.length}</span>}
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        <Tabs.Content value="racks" className="space-y-4 outline-none">
          <Panel title="North Lab · Row A" sub="Select a device to open its record"
            actions={<>
              <div className="flex rounded-lg border border-line p-0.5" role="group" aria-label="Rack face">
                {(["front", "rear"] as const).map((f) => <button key={f} onClick={() => setFace(f)} aria-pressed={face === f} className={clsx("rounded-md px-2.5 py-1 text-[12px] font-medium capitalize", face === f ? "bg-nav text-white" : "text-ink-2")}>{f}</button>)}
              </div>
              <button className="btn-ghost btn-sm" onClick={() => setText((t) => !t)} aria-pressed={text}>{text ? "Visual" : "Text view"}</button>
            </>}>
            {racks.isLoading ? <LoadingBlock rows={10} /> : racks.error ? <ErrorState error={racks.error} /> : text ? (
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">{racks.data!.map((r) => <div key={r.id} className="overflow-x-auto"><div className="eyebrow mb-1">{r.display_id}</div><RackTable rack={r} /></div>)}</div>
            ) : (
              <div className="mx-auto grid max-w-[980px] gap-8 md:grid-cols-2">
                {racks.data!.map((r) => (
                  <div key={r.id}>
                    <div className="mb-2 flex items-baseline justify-between"><span className="mono text-[14px] font-semibold">{r.display_id}</span><span className="text-[12px] text-ink-2">{r.u_height}U · {r.free_units}U free</span></div>
                    <RackElevation rack={r} face={face} selected={selected} onSelect={(d) => setParams((p) => { p.set("device", d.display_id); return p; })} />
                  </div>
                ))}
              </div>
            )}
          </Panel>
          <Panel title="Place or move a device" icon={<MoveVertical className="h-4 w-4" />}><PlaceDevice /></Panel>
        </Tabs.Content>

        <Tabs.Content value="cables" className="space-y-4 outline-none">
          {(audit.data?.issues.length ?? 0) > 0 && (
            <Panel title="Documentation defects" icon={<ShieldAlert className="h-4 w-4 text-warn" />} sub="Found by validating the cable model">
              <ul className="space-y-1.5">
                {audit.data!.issues.map((i, k) => (
                  <li key={k} className="flex items-start gap-2 text-[12.5px]">
                    <Pill className={i.severity === "critical" ? "border-crit/30 bg-crit-50 text-crit" : "border-warn/30 bg-warn-50 text-warn"}>{i.code.replace(/_/g, " ")}</Pill>
                    <span className="text-ink">{i.message}</span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
          <Panel title="Cable explorer" icon={<CableIcon className="h-4 w-4" />} actions={<button className="btn-primary btn-sm" onClick={() => setRecordOpen(true)}><Plus className="h-3.5 w-3.5" aria-hidden />Record cable</button>} bodyClass="">
            {cables.isLoading ? <LoadingBlock /> : (
              <div className="overflow-x-auto">
                <table className="table">
                  <thead><tr><th scope="col">Label</th><th scope="col">Type</th><th scope="col">Endpoint A</th><th scope="col">Endpoint B</th><th scope="col">Intended</th><th scope="col">Status</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
                  <tbody>
                    {cables.data!.map((c) => (
                      <tr key={c.id} className={clsx(trace?.cable === c.id && "bg-accent-50/60")}>
                        <td className="mono font-medium">{c.label ?? <span className="text-warn">UNLABELED</span>}{issuesByCable.get(c.id)?.some((i) => i.code === "incompatible_connector") && <span className="ml-1 text-[10.5px] text-crit" title="Incompatible connector recorded">⚠ connector</span>}</td>
                        <td className="mono text-ink-2">{c.cable_type}</td>
                        <td className="mono">{c.a.device}:{c.a.interface}</td>
                        <td className="mono">{c.b.device}:{c.b.interface}</td>
                        <td className="mono text-ink-2">{c.intended_speed_mbps ? `${c.intended_speed_mbps / 1000}G` : "—"}</td>
                        <td>{c.status}</td>
                        <td className="whitespace-nowrap text-right">
                          <button className="btn-ghost btn-sm" onClick={() => { setParams((p) => { p.set("cable", String(c.id)); return p; }); runTrace(c); }} aria-label={`Trace ${c.label ?? "unlabeled cable"}`}><Route className="h-3.5 w-3.5" aria-hidden />Trace</button>
                          {!c.label && <button className="btn-ghost btn-sm" onClick={() => { setLabelFor(c); setNewLabel("CBL-0103"); }}><Tag className="h-3.5 w-3.5" aria-hidden />Label</button>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
          {trace && <Panel title="Traced path" icon={<Route className="h-4 w-4" />}><CableTrace key={trace.cable} trace={trace.t} /></Panel>}
        </Tabs.Content>

        <Tabs.Content value="power" className="space-y-4 outline-none">
          {power.isLoading ? <LoadingBlock /> : power.data && (
            <>
              <Panel title="Feeds" icon={<Zap className="h-4 w-4" />} sub={power.data.basis} bodyClass="overflow-x-auto">
                <table className="table">
                  <thead><tr><th scope="col">Feed</th><th scope="col">Upstream source</th><th scope="col" className="text-right">Modeled capacity</th><th scope="col" className="text-right">Estimated load</th><th scope="col">Utilization (estimate)</th></tr></thead>
                  <tbody>
                    {power.data.feeds.map((f: any) => (
                      <tr key={f.feed}>
                        <td><div className="mono font-medium">{f.feed}</div><div className="text-[11.5px] text-ink-2">{f.name}</div></td>
                        <td>{f.upstream ?? <span className="font-medium text-warn">Unknown</span>}</td>
                        <td className="mono text-right">{f.capacity_w ? `${f.capacity_w} W` : "Unknown"}</td>
                        <td className="mono text-right">{f.estimated_load_w !== null ? `~${f.estimated_load_w} W` : "Not modeled"}</td>
                        <td className="w-[220px]">{f.utilization_pct_estimate !== null ? (
                          <div className="flex items-center gap-2"><div className="h-1.5 flex-1 overflow-hidden rounded-full bg-line-soft"><motion.div className="h-full rounded-full bg-accent" initial={{ width: 0 }} animate={{ width: `${Math.min(f.utilization_pct_estimate, 100)}%` }} transition={{ duration: 0.5 }} /></div><span className="mono text-[11.5px]">~{f.utilization_pct_estimate}%</span></div>
                        ) : <span className="text-[12px] text-ink-3">Cannot compute</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Panel>
              <Panel title="Power findings" icon={<ShieldAlert className="h-4 w-4 text-warn" />} sub="Two different PDU names do not prove independent power">
                {power.data.issues.length === 0 ? <Empty title="No power findings" /> : (
                  <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
                    {power.data.issues.map((i: any, k: number) => (
                      <motion.li key={k} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: k * 0.05 }}
                        className={clsx("rounded-xl border p-3", i.severity === "critical" ? "border-crit/30 bg-crit-50/40" : "border-warn/30 bg-warn-50/40")}>
                        <div className="flex items-center gap-2"><Pill className={i.severity === "critical" ? "border-crit/30 bg-white text-crit" : "border-warn/30 bg-white text-warn"}>{i.code.replace(/_/g, " ")}</Pill>
                          <button className="mono text-[12.5px] font-semibold text-accent-700 hover:underline" onClick={() => setParams({ tab: "racks", device: i.device })}>{i.device}</button></div>
                        <p className="mt-1.5 text-[12.5px] text-ink">{i.message}</p>
                      </motion.li>
                    ))}
                  </ul>
                )}
                <p className="mt-3 text-[11.5px] text-ink-2">Documentation model only: not an electrical design certification. Loads are estimates taken from modeled PSU draw, not metered readings.</p>
              </Panel>
            </>
          )}
        </Tabs.Content>

        <Tabs.Content value="labels" className="space-y-4 outline-none">
          <Panel title="Printable labels" sub="QR codes link to the local record route" actions={<button className="btn-primary btn-sm no-print" onClick={() => window.print()}><Printer className="h-3.5 w-3.5" aria-hidden />Print labels</button>}>
            <div className="eyebrow mb-2">Devices</div>
            <div className="flex flex-wrap gap-3">
              {(racks.data ?? []).flatMap((r) => r.devices).filter((d) => d.asset_id).map((d) => <QrLabel key={d.display_id} title={d.display_id} subtitle={`${d.asset} · ${d.rack} U${d.position_u}`} path={`/assets/${d.asset_id}`} />)}
            </div>
            <div className="eyebrow mb-2 mt-5">Cables (both ends)</div>
            <div className="flex flex-wrap gap-3">
              {(cables.data ?? []).filter((c) => c.label).map((c) => <QrLabel key={c.id} title={c.label!} subtitle={`${c.a.device}:${c.a.interface} ↔ ${c.b.device}:${c.b.interface}`} path={`/infrastructure?cable=${c.id}`} />)}
            </div>
            {(cables.data ?? []).some((c) => !c.label) && <p className="mt-3 text-[12px] text-warn">Unlabeled cables have no printable label until a label is recorded.</p>}
          </Panel>
        </Tabs.Content>
      </Tabs.Root>

      <DeviceDrawer id={selected} onClose={() => setParams((p) => { p.delete("device"); return p; })} />
      <RecordCable open={recordOpen} onOpenChange={setRecordOpen} />
      <Modal open={!!labelFor} onOpenChange={(o) => !o && setLabelFor(null)} title="Label cable" description={labelFor ? `${labelFor.a.device}:${labelFor.a.interface} ↔ ${labelFor.b.device}:${labelFor.b.interface}` : ""}>
        <form onSubmit={(e) => { e.preventDefault(); doLabel.mutate(); }} className="space-y-3">
          <Field label="Label" htmlFor="nl" hint="Uppercase letters, digits and hyphens. Must be unique."><input id="nl" className="input font-mono" value={newLabel} onChange={(e) => setNewLabel(e.target.value.toUpperCase())} /></Field>
          <div className="flex justify-end gap-2"><button type="button" className="btn-secondary" onClick={() => setLabelFor(null)}>Cancel</button><button className="btn-primary" disabled={newLabel.length < 3 || doLabel.isPending}>Save label</button></div>
        </form>
      </Modal>
    </div>
  );
}
