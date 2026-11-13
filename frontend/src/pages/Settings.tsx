import clsx from "clsx";
import { FileInput, History, Plus, Power, PowerOff, Save, Server, Trash2, Upload, UserRound, Workflow } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, post, put } from "@/api/client";
import { useAction, useAudit, useProfile, useSettings } from "@/api/hooks";
import { AuditList } from "@/components/rack/DevicePanel";
import { Pill, SourceBadge } from "@/components/ui/Badges";
import { useToast } from "@/components/ui/Toast";
import { ErrorState, Field, KV, LoadingBlock, PageHeader, Panel } from "@/components/ui/Primitives";
import { useQueryClient } from "@tanstack/react-query";

const STATUS_CLS: Record<string, string> = {
  configured: "border-ok/30 bg-ok-50 text-ok",
  enabled: "border-ok/30 bg-ok-50 text-ok",
  unconfigured: "border-line-strong bg-canvas text-ink-2",
  disabled: "border-line-strong bg-canvas text-ink-2",
  fixture: "border-imp/25 bg-imp-50 text-imp",
};
function statusPill(s: string) {
  const key = s.startsWith("fixture") ? "fixture" : s.startsWith("enabled") ? "enabled" : s;
  return <Pill className={STATUS_CLS[key] ?? STATUS_CLS.unconfigured}>{s}</Pill>;
}

function ProfileForm() {
  const p = useProfile();
  const [f, setF] = useState({ name: "", headline: "", summary: "", operator_name: "operator", links: [] as { label: string; url: string }[] });
  useEffect(() => {
    if (p.data) setF({ name: p.data.name, headline: p.data.headline, summary: p.data.summary, operator_name: p.data.operator_name, links: p.data.links ?? [] });
  }, [p.data]);
  const save = useAction(() => put("/profile", f), { success: "Candidate profile saved" });
  if (p.isLoading) return <LoadingBlock rows={5} />;
  if (p.error) return <ErrorState error={p.error} retry={() => p.refetch()} />;
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Field label="Candidate name" htmlFor="pf-name" hint="Shown on the portfolio overview and sidebar."><input id="pf-name" className="input" required maxLength={120} value={f.name} onChange={set("name")} /></Field>
        <Field label="Operator name" htmlFor="pf-op" hint="Recorded as the actor on actions you take (audit log, timelines)."><input id="pf-op" className="input" required maxLength={80} value={f.operator_name} onChange={set("operator_name")} /></Field>
      </div>
      <Field label="Headline" htmlFor="pf-head"><input id="pf-head" className="input" maxLength={200} value={f.headline} onChange={set("headline")} /></Field>
      <Field label="Summary" htmlFor="pf-sum" hint="Your own words. Nothing here is generated."><textarea id="pf-sum" className="input" rows={3} maxLength={4000} value={f.summary} onChange={set("summary")} /></Field>
      <fieldset>
        <legend className="label">Links</legend>
        <ul className="space-y-2">
          {f.links.map((l, i) => (
            <li key={i} className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1.5fr_auto]">
              <label className="sr-only" htmlFor={`ln-l-${i}`}>Link {i + 1} label</label>
              <input id={`ln-l-${i}`} className="input" placeholder="Label" value={l.label} onChange={(e) => setF({ ...f, links: f.links.map((x, k) => (k === i ? { ...x, label: e.target.value } : x)) })} />
              <label className="sr-only" htmlFor={`ln-u-${i}`}>Link {i + 1} URL</label>
              <input id={`ln-u-${i}`} className="input mono" placeholder="https://…" value={l.url} onChange={(e) => setF({ ...f, links: f.links.map((x, k) => (k === i ? { ...x, url: e.target.value } : x)) })} />
              <button type="button" className="btn-ghost h-9" aria-label={`Remove link ${i + 1}`} onClick={() => setF({ ...f, links: f.links.filter((_, k) => k !== i) })}><Trash2 className="h-4 w-4" /></button>
            </li>
          ))}
        </ul>
        <button type="button" className="btn-ghost btn-sm mt-2" onClick={() => setF({ ...f, links: [...f.links, { label: "", url: "" }] })}><Plus className="h-3.5 w-3.5" aria-hidden />Add link</button>
      </fieldset>
      <div className="flex flex-wrap items-center gap-3 border-t border-line-soft pt-3">
        <button className="btn-primary" disabled={save.isPending}><Save className="h-4 w-4" aria-hidden />Save profile</button>
        <span className="text-[12px] text-ink-2">Candidate contribution and lessons learned are edited on each case study:
          {" "}<Link className="text-accent-700 hover:underline" to="/projects/incident-recovery">1</Link>,
          {" "}<Link className="text-accent-700 hover:underline" to="/projects/server-acceptance">2</Link>,
          {" "}<Link className="text-accent-700 hover:underline" to="/projects/rack-lifecycle">3</Link>.</span>
      </div>
    </form>
  );
}

const ENV: Record<string, string> = {
  redfish: "RACKOPS_REDFISH_URL, _USERNAME, _PASSWORD, _VERIFY_TLS",
  netbox: "RACKOPS_NETBOX_URL, RACKOPS_NETBOX_TOKEN",
  alertmanager: "RACKOPS_ALERTMANAGER_WEBHOOK_ENABLED, _TOKEN",
  jira: "RACKOPS_JIRA_URL, RACKOPS_JIRA_TOKEN",
  notifications: "RACKOPS_NOTIFICATIONS_ENABLED",
};

function Integrations({ s }: { s: any }) {
  const ints = s.integrations ?? {};
  const counts = s.source_counts ?? {};
  const srcs = ["SIMULATED", "LOCAL_LAB", "IMPORTED_SAMPLE"];
  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-1 gap-x-6 divide-y divide-line-soft sm:grid-cols-3 sm:divide-y-0">
        <KV k="Mode" v={s.mode === "public_preview" ? "Read-only public preview" : "Local, single user"} />
        <KV k="API bind host" v={s.bind_host} mono />
        <KV k="Probe interval" v={`${s.simulation?.probe_interval_s} s (deterministic)`} />
      </dl>
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="table">
          <caption className="sr-only">Integration status</caption>
          <thead><tr><th scope="col">Integration</th><th scope="col">Status</th><th scope="col">Configure with</th><th scope="col">Notes</th></tr></thead>
          <tbody>
            {Object.entries(ints).map(([k, v]: [string, any]) => (
              <tr key={k}>
                <td className="font-medium capitalize">{k}</td>
                <td>{statusPill(String(v.status))}</td>
                <td className="mono text-[11px] text-ink-2">{ENV[k] ?? "—"}</td>
                <td className="text-[12px] text-ink-2">
                  {k === "redfish" && <>Mode <span className="mono">{v.mode}</span> · TLS verify {v.verify_tls ? "on" : "off"}{v.base_url && <> · <span className="mono">{v.base_url}</span></>}. Read-only GET adapter.</>}
                  {k === "alertmanager" && <>Endpoint <span className="mono">{v.endpoint}</span> · {v.auth}</>}
                  {(k === "netbox" || k === "jira") && v.note}
                  {k === "notifications" && "No external notification is ever sent by default."}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[12px] text-ink-2">Credentials are read from the environment and never returned by the API. Without credentials, local workflows keep working and the integration is shown as unconfigured.</p>
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="table">
          <caption className="sr-only">Record counts by source</caption>
          <thead><tr><th scope="col">Records</th>{srcs.map((x) => <th key={x} scope="col" className="text-right"><SourceBadge source={x} compact /></th>)}</tr></thead>
          <tbody>
            {Object.entries(counts).map(([t, c]: [string, any]) => (
              <tr key={t}><td className="mono">{t}</td>{srcs.map((x) => <td key={x} className="mono text-right">{c[x] ?? 0}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function LiveLab({ s }: { s: any }) {
  const ll = s.livelab ?? {};
  const st = ll.status;
  const toggle = useAction(() => post("/settings/livelab", { enabled: !ll.enabled }), { success: ll.enabled ? "Live lab disabled" : "Live lab enabled: target started on 127.0.0.1" });
  const action = useAction((a: "stop" | "start") => post(`/livelab/${a}`), {
    success: (r: any) => (r?.health?.ok ? "Lab target is responding" : "Lab target stopped. A LOCAL LAB incident opens after 2 failed probes."),
  });
  return (
    <div className="space-y-3">
      <p className="text-[13px] leading-relaxed text-ink">
        Opt-in. The backend starts its own tiny HTTP process bound to <span className="mono">127.0.0.1{st?.port ? `:${st.port}` : ""}</span> and probes it every few seconds.
        Stopping it is a <b>real</b> outage exercise: evidence and metrics are labeled <SourceBadge source="LOCAL_LAB" compact />. It never inspects or changes other host services,
        fills disks, stresses the CPU or touches network interfaces.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <button className={ll.enabled ? "btn-secondary" : "btn-primary"} disabled={toggle.isPending} onClick={() => toggle.mutate()} aria-pressed={!!ll.enabled}>
          {ll.enabled ? <><PowerOff className="h-4 w-4" aria-hidden />Disable live lab</> : <><Power className="h-4 w-4" aria-hidden />Enable live lab</>}
        </button>
        <Pill className={ll.enabled ? "border-lab/25 bg-lab-50 text-lab" : "border-line-strong bg-canvas text-ink-2"}>{ll.enabled ? "Enabled" : "Disabled (default)"}</Pill>
      </div>
      {ll.enabled && st && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto] md:items-start">
          <dl className="divide-y divide-line-soft rounded-xl border border-line px-3">
            <KV k="Recorded PID" v={st.pid ?? "—"} mono />
            <KV k="Process alive" v={st.pid_alive ? "Yes" : "No"} />
            <KV k="GET /health" v={st.health?.ok ? `HTTP ${st.health.status_code} · ${st.health.latency_ms} ms` : st.health?.error ?? "No response"} mono />
            <KV k="URL" v={st.health?.url} mono />
          </dl>
          <div className="flex flex-wrap gap-2 md:flex-col">
            <button className="btn-danger" disabled={action.isPending || !st.health?.ok} onClick={() => action.mutate("stop")}><PowerOff className="h-4 w-4" aria-hidden />Stop target (real outage drill)</button>
            <button className="btn-secondary" disabled={action.isPending || st.health?.ok} onClick={() => action.mutate("start")}><Power className="h-4 w-4" aria-hidden />Start target</button>
          </div>
        </div>
      )}
      <p className="text-[12px] text-ink-2">After 2 consecutive failed real probes a LOCAL LAB incident appears in the <Link className="text-accent-700 hover:underline" to="/incidents?source=LOCAL_LAB">incident queue</Link>.
        Fault onset is known only when you stopped the target from here.</p>
    </div>
  );
}

function Imports() {
  const toast = useToast();
  const qc = useQueryClient();
  const file = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const sample = useAction(() => post<{ created: string[]; updated: string[] }>("/integrations/alertmanager/sample"), {
    success: (r) => (r.created.length ? `Imported ${r.created.join(", ")} (IMPORTED SAMPLE)` : "Sample already imported; no duplicate created"),
  });
  const upload = async () => {
    const f = file.current?.files?.[0];
    if (!f) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const res = await fetch("/api/integrations/netbox/import", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new ApiError(res.status, data?.error?.code ?? "http_error", data?.error?.message ?? `Upload failed (${res.status})`);
      toast.push({ tone: "ok", title: `NetBox import: ${data.created.length} created, ${data.skipped.length} skipped` });
      qc.invalidateQueries();
      if (file.current) file.current.value = "";
    } catch (e) {
      toast.push({ tone: "error", title: e instanceof Error ? e.message : "Upload failed" });
    } finally { setBusy(false); }
  };
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <div className="rounded-xl border border-line p-3">
        <div className="flex items-center gap-2"><span className="font-semibold">Alertmanager sample</span><SourceBadge source="IMPORTED_SAMPLE" compact /></div>
        <p className="mt-1 text-[12.5px] text-ink-2">Loads a bundled example webhook payload as an incident labeled IMPORTED SAMPLE. It does not describe any device in this lab, and its fault onset is unknown.</p>
        <button className="btn-secondary btn-sm mt-3" disabled={sample.isPending} onClick={() => sample.mutate()}><FileInput className="h-3.5 w-3.5" aria-hidden />Import sample alert</button>
      </div>
      <div className="rounded-xl border border-line p-3">
        <div className="flex items-center gap-2"><span className="font-semibold">NetBox device export (read-only)</span><SourceBadge source="IMPORTED_SAMPLE" compact /></div>
        <p className="mt-1 text-[12.5px] text-ink-2">Upload a <span className="mono">/api/dcim/devices/</span> JSON response. Devices are created as imported and are not placed in a rack. Sample file: <span className="mono break-all">backend/app/fixtures/netbox_devices_sample.json</span>.</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <label htmlFor="nb-file" className="sr-only">NetBox JSON file</label>
          <input id="nb-file" ref={file} type="file" accept="application/json,.json" className="text-[12px] file:mr-2 file:rounded-md file:border file:border-line file:bg-white file:px-2 file:py-1 file:text-[12px]" />
          <button className="btn-secondary btn-sm" disabled={busy} onClick={upload}><Upload className="h-3.5 w-3.5" aria-hidden />Import</button>
        </div>
      </div>
    </div>
  );
}

const ORIGINS = ["all", "simulation", "operator", "seed", "imported", "local_lab"];

function AuditSection() {
  const [origin, setOrigin] = useState("all");
  const a = useAudit(`limit=100${origin !== "all" ? `&origin=${origin}` : ""}`);
  return (
    <Panel id="audit" title="Audit log" icon={<History className="h-4 w-4" />} sub={a.data ? `${a.data.total} event(s)` : undefined}
      actions={
        <div className="flex flex-wrap gap-1" role="group" aria-label="Filter by origin">
          {ORIGINS.map((o) => (
            <button key={o} onClick={() => setOrigin(o)} aria-pressed={origin === o}
              className={clsx("h-6 rounded-full border px-2 text-[11px] font-medium", origin === o ? "border-accent bg-accent text-white" : "border-line text-ink-2 hover:text-ink")}>{o.replace("_", " ")}</button>
          ))}
        </div>
      }
      bodyClass="max-h-[560px] overflow-y-auto p-4">
      {a.isLoading ? <LoadingBlock rows={6} /> : a.error ? <ErrorState error={a.error} retry={() => a.refetch()} /> : <AuditList items={a.data?.items ?? []} />}
    </Panel>
  );
}

export function SettingsPage() {
  const s = useSettings();
  useEffect(() => {
    if (window.location.hash === "#audit") setTimeout(() => document.getElementById("audit")?.scrollIntoView({ behavior: "smooth" }), 300);
  }, []);
  return (
    <div className="space-y-5">
      <PageHeader title="Settings">
        Profile, data sources and integrations. Real observations are labeled LOCAL LAB.
      </PageHeader>
      <Panel title="Candidate profile" icon={<UserRound className="h-4 w-4" />}><ProfileForm /></Panel>
      <Panel title="Data sources & integrations" icon={<Workflow className="h-4 w-4" />}>
        {s.isLoading ? <LoadingBlock rows={6} /> : s.error ? <ErrorState error={s.error} retry={() => s.refetch()} /> : <Integrations s={s.data} />}
      </Panel>
      <Panel title="Live lab (opt-in)" icon={<Server className="h-4 w-4" />}>
        {s.isLoading ? <LoadingBlock rows={3} /> : s.data && <LiveLab s={s.data} />}
      </Panel>
      <Panel title="Imports" icon={<FileInput className="h-4 w-4" />}><Imports /></Panel>
      <AuditSection />
      <Panel title="Simulation data">
        <p className="text-[13px] text-ink-2">To reset simulation-owned records (demos and drills) without touching imported or local-lab evidence, use
          {" "}<Link to="/demo" className="font-medium text-accent-700 hover:underline">Demonstrations → Reset all simulation data</Link>.</p>
      </Panel>
    </div>
  );
}
