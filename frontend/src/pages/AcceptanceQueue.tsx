import clsx from "clsx";
import { motion } from "framer-motion";
import { ClipboardCheck, Plus, Server } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { post } from "@/api/client";
import { useAction, useIntakes, useProfiles, useRacks } from "@/api/hooks";
import type { Intake } from "@/api/types";
import { Pill, ResultBadge, SourceBadge } from "@/components/ui/Badges";
import { Empty, ErrorState, Field, LoadingBlock, Modal, PageHeader, Panel } from "@/components/ui/Primitives";
import { fmtDateTime } from "@/lib/format";

export const INTAKE_STATUS: Record<string, { label: string; cls: string }> = {
  awaiting_acceptance: { label: "Awaiting acceptance", cls: "border-line-strong bg-canvas text-ink-2" },
  failed: { label: "Failed", cls: "border-crit/30 bg-crit-50 text-crit" },
  manual_review: { label: "Manual review", cls: "border-warn/30 bg-warn-50 text-warn" },
  accepted: { label: "Accepted", cls: "border-ok/30 bg-ok-50 text-ok" },
  handed_off: { label: "Handed off", cls: "border-accent/30 bg-accent-50 text-accent-700" },
};
export const IntakeStatus = ({ s }: { s: string }) => <Pill className={INTAKE_STATUS[s]?.cls ?? INTAKE_STATUS.awaiting_acceptance.cls}>{INTAKE_STATUS[s]?.label ?? s}</Pill>;

function NewIntake({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const nav = useNavigate();
  const racks = useRacks();
  const [f, setF] = useState({ asset_tag: "NL-AST-0008", serial_number: "SIM-NL1U-0008", hostname: "lab-srv-08", cpu_count: 2, cpu_model: "Northwind NX-16",
    memory_gib: 128, disk_count: 2, disk_gb: 960, nic_count: 2, speed: 10000, rack: "NL-R02", u: 16 });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF((x) => ({ ...x, [k]: typeof x[k] === "number" ? Number(e.target.value) : e.target.value }));
  const create = useAction(() => post<Intake>("/acceptance/intakes", {
    asset_tag: f.asset_tag, serial_number: f.serial_number, hostname: f.hostname, intended_rack: f.rack || null, intended_position_u: f.u || null,
    expected: { cpu_count: f.cpu_count, cpu_model: f.cpu_model, memory_gib: f.memory_gib, storage: [{ count: f.disk_count, size_gb: f.disk_gb, type: "nvme" }], nic_count: f.nic_count, data_link_speed_mbps: f.speed },
    source_type: "SIMULATED", use_simulator_model: true,
  }), { success: "Intake recorded", onSuccess: (r) => { onOpenChange(false); nav(`/acceptance/${r.id}`); } });
  const inp = (k: keyof typeof f, label: string, type = "text", hint?: string) => (
    <Field label={label} htmlFor={`ni-${k}`} hint={hint}><input id={`ni-${k}`} className={clsx("input", type === "text" && "font-mono text-[12.5px]")} type={type} value={f[k]} onChange={set(k)} /></Field>
  );
  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Record server intake" description="Define what “correct” means before measuring anything. New intakes use the simulator's hardware model unless you upload collector output." wide>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">{inp("asset_tag", "Asset tag")}{inp("serial_number", "Serial number")}{inp("hostname", "Hostname", "text", "lowercase, digits, hyphens")}</div>
        <div className="eyebrow pt-1">Expected configuration</div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {inp("cpu_count", "CPU sockets", "number")}{inp("cpu_model", "CPU model contains")}{inp("memory_gib", "Memory (GiB)", "number")}
          {inp("disk_count", "NVMe drives", "number")}{inp("disk_gb", "Drive size (GB)", "number")}{inp("nic_count", "NIC count", "number")}
          {inp("speed", "Data link speed (Mb/s)", "number")}
          <Field label="Intended rack" htmlFor="ni-rack">
            <select id="ni-rack" className="input" value={f.rack} onChange={set("rack")}><option value="">Not decided</option>{racks.data?.map((r) => <option key={r.id} value={r.display_id}>{r.display_id}</option>)}</select>
          </Field>
          {inp("u", "Intended U position", "number", "Validated against occupied units")}
        </div>
        <div className="flex justify-end gap-2 pt-2"><button type="button" className="btn-secondary" onClick={() => onOpenChange(false)}>Cancel</button><button className="btn-primary" disabled={create.isPending}>Create intake</button></div>
      </form>
    </Modal>
  );
}

export function AcceptanceQueue() {
  const q = useIntakes();
  const profiles = useProfiles();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const [open, setOpen] = useState(false);
  const status = params.get("status");
  const attention = params.get("attention") === "1";
  const rows = (q.data ?? []).filter((x) => (attention ? ["failed", "manual_review"].includes(x.status) : !status || x.status === status));

  return (
    <div className="space-y-5">
      <PageHeader title="Acceptance"
        actions={<button className="btn-primary" onClick={() => setOpen(true)}><Plus className="h-4 w-4" aria-hidden />New intake</button>}>
        New servers checked against their build sheet before provisioning.
      </PageHeader>

      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by status">
        {[null, ...Object.keys(INTAKE_STATUS)].map((s) => (
          <button key={s ?? "all"} onClick={() => setParams(s ? { status: s } : {})} aria-pressed={!attention && status === s}
            className={clsx("h-7 rounded-full border px-2.5 text-[12px] font-medium", !attention && status === s ? "border-accent bg-accent text-white" : "border-line bg-white text-ink-2 hover:text-ink")}>
            {s ? INTAKE_STATUS[s].label : "All"} <span className="opacity-70">({(q.data ?? []).filter((x) => !s || x.status === s).length})</span>
          </button>
        ))}
        <button onClick={() => setParams({ attention: "1" })} aria-pressed={attention}
          className={clsx("h-7 rounded-full border px-2.5 text-[12px] font-medium", attention ? "border-warn bg-warn text-white" : "border-line bg-white text-ink-2 hover:text-ink")}>
          Needs attention ({(q.data ?? []).filter((x) => ["failed", "manual_review"].includes(x.status)).length})
        </button>
      </div>

      {q.isLoading ? <LoadingBlock rows={5} /> : q.error ? <ErrorState error={q.error} retry={() => q.refetch()} /> : rows.length === 0 ? (
        <div className="panel"><Empty title="No intakes with this status" icon={<Server className="h-5 w-5" />} /></div>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {rows.map((x, i) => {
            const last = x.runs.at(-1);
            return (
              <motion.button key={x.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05, duration: 0.22 }} whileHover={{ y: -2 }}
                onClick={() => nav(`/acceptance/${x.id}`)} className="panel flex flex-col p-4 text-left transition-shadow hover:shadow-lift">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="mono text-[15px] font-semibold text-ink">{x.hostname}</div>
                    <div className="mono text-[11.5px] text-ink-2">{x.display_id} · {x.asset_tag} · {x.serial_number}</div>
                  </div>
                  <IntakeStatus s={x.status} />
                </div>
                <dl className="mt-3 grid grid-cols-3 gap-2 text-[12px]">
                  <div><dt className="text-ink-2">Memory</dt><dd className="mono">{x.expected.memory_gib} GiB</dd></div>
                  <div><dt className="text-ink-2">Data link</dt><dd className="mono">{x.expected.data_link_speed_mbps / 1000} Gb/s</dd></div>
                  <div><dt className="text-ink-2">Planned</dt><dd className="mono">{x.intended_rack ? `${x.intended_rack} U${x.intended_position_u}` : "—"}</dd></div>
                </dl>
                <div className="mt-3 flex items-center gap-2 border-t border-line-soft pt-3 text-[12px]">
                  {last ? <><span className="text-ink-2">Run #{last.run_number}</span><ResultBadge result={last.status === "completed" ? last.disposition : null} /><SourceBadge source={last.source_type} compact /><span className="mono ml-auto text-ink-3">{fmtDateTime(last.completed_at ?? last.created_at).slice(5, 16)}</span></>
                    : <span className="text-ink-2">No runs yet</span>}
                </div>
              </motion.button>
            );
          })}
        </div>
      )}

      <Panel title="Acceptance profile" icon={<ClipboardCheck className="h-4 w-4" />} sub={profiles.data?.[0] ? `${profiles.data[0].name} · v${profiles.data[0].version}` : undefined} bodyClass="overflow-x-auto">
        {profiles.data?.[0] && (
          <table className="table">
            <thead><tr><th scope="col">Check</th><th scope="col">Version</th><th scope="col">Gate</th><th scope="col">What it verifies</th></tr></thead>
            <tbody>{profiles.data[0].checks.map((c: any) => (
              <tr key={c.check_key}><td className="font-medium">{c.name}</td><td className="mono text-ink-2">v{c.version}</td>
                <td>{c.required ? <Pill className="border-accent/30 bg-accent-50 text-accent-700">Required</Pill> : <Pill className="border-line bg-white text-ink-2">Optional</Pill>}</td>
                <td className="text-[12.5px] text-ink-2">{c.description}</td></tr>
            ))}</tbody>
          </table>
        )}
      </Panel>
      <p className="text-[12px] text-ink-2">Optional checks are always shown but never change the disposition. Missing data is shown as “Not collected”, never as zero. <Link className="text-accent-700 hover:underline" to="/runbooks/server-acceptance">Acceptance runbook →</Link></p>
      <NewIntake open={open} onOpenChange={setOpen} />
    </div>
  );
}
