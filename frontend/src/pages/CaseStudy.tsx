import clsx from "clsx";
import { motion } from "framer-motion";
import { ArrowRight, Check, PlayCircle, Printer, Save, ShieldCheck } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { post, put } from "@/api/client";
import { useAction, useProfile, useProjectResults } from "@/api/hooks";
import type { SourceType } from "@/api/types";
import { Pill, ResultBadge, SourceBadge } from "@/components/ui/Badges";
import { CopyButton, Empty, ErrorState, LoadingBlock } from "@/components/ui/Primitives";
import { fmtDateTime } from "@/lib/format";
import { MetricsPanel } from "./IncidentQueue";
import { PROJECTS } from "./About";

interface Detail {
  relevance: string[];
  workflow: { t: string; d: string }[];
  arch: { services: string[]; tables: string[]; external: string };
  script: string[];
  limitations: string[];
}

const DETAILS: Record<string, Detail> = {
  "incident-recovery": {
    relevance: [
      "Technicians are often first to see a failure. Good first response means clear evidence and correct escalation, not guesswork.",
      "An unreachable server has several possible causes (service, path, cable, port, NIC). Discriminating checks keep the wrong part from being replaced.",
      "Recovery has to be shown with checks over time. Restarting something and hoping is not recovery.",
      "Detection and recovery intervals are only meaningful when each timestamp is defined and recorded.",
    ],
    workflow: [
      { t: "Detect", d: "Rule fires after 2 failed probes" },
      { t: "Acknowledge", d: "Ownership and ack latency" },
      { t: "Investigate", d: "Evidence, then hypotheses" },
      { t: "Repair", d: "Recorded corrective action" },
      { t: "Verify", d: "Checks + 2 healthy probes" },
      { t: "Resolve", d: "Summary from records" },
    ],
    arch: {
      services: ["services/incidents.py", "services/scenarios.py", "services/simulation.py", "collectors/sim_evidence.py", "livelab/manager.py"],
      tables: ["incidents", "incident_events", "hypotheses", "repair_actions", "verifications", "evidence_items", "metric_observations", "simulation_runs"],
      external: "Optional: Alertmanager webhook, live-lab target on 127.0.0.1",
    },
    script: [
      "Start the demo. The baseline probes against lab-srv-02 are healthy.",
      "The simulator stops inventory-api, and the rule detects it after 2 failed probes (detection latency ≈ 3 s).",
      "Acknowledge, then collect the HTTP check, systemctl and journal. Point out 'refused' vs 'timeout'.",
      "Try the wrong hypothesis (bounce eth1). Verification fails and the incident returns to investigation.",
      "Start the service, wait for 2 healthy probes, verify, resolve, then open the post-incident summary.",
    ],
    limitations: [
      "Default evidence is rendered by the simulator from scenario state. It shows realistic command output, not output collected from a host.",
      "Scenario timing uses a 3 s probe interval, so drill intervals are much shorter than real incidents and are not comparable to production MTTR.",
      "The live lab exercises only a lab-owned HTTP process. It does not fill disks, stress CPUs or disable interfaces on this machine.",
      "No paging, on-call rotation or notification channel is implemented. External notifications are disabled.",
    ],
  },
  "server-acceptance": {
    relevance: [
      "Hardware arrives with wrong DIMM population, optics or drives more often than expected. Finding it at intake is far cheaper than finding it in production.",
      "Provisioning teams need evidence that a machine matches its build sheet, not a verbal 'looks good'.",
      "Missing evidence (no root access, BMC without a property) must stop for review, not pass silently.",
      "Re-tests after corrections must leave the original failure on record for vendor discrepancy claims.",
    ],
    workflow: [
      { t: "Intake", d: "Expected config recorded" },
      { t: "Snapshot", d: "Observations frozen" },
      { t: "Checks", d: "10 modular checks" },
      { t: "Disposition", d: "Explicit required-check rules" },
      { t: "Correct", d: "Labeled corrections" },
      { t: "Re-test", d: "New immutable run" },
      { t: "Handoff", d: "Checklist to provisioning" },
    ],
    arch: {
      services: ["acceptance/checks.py", "services/acceptance.py", "collectors/redfish.py", "collectors/rackops_collect.py (operator-run, repo root)", "templates/acceptance_report.html"],
      tables: ["intake_records", "acceptance_profiles", "acceptance_runs", "acceptance_check_results", "evidence_items"],
      external: "Optional: read-only Redfish endpoint (GET only), uploaded Linux collector JSON",
    },
    script: [
      "Open INT-0001: lab-srv-06 is expected to have 128 GiB RAM, 2 NICs and a 10 Gb/s data link.",
      "Run acceptance #1. The job runner executes the checks and the result is FAIL (64 GiB, 1000 Mb/s).",
      "Show that optional checks stay visible but do not decide the result, and that 'Not collected' is never zero.",
      "Record the two labeled simulated corrections, then start run #2. It passes.",
      "Open the side-by-side diff and the printable report. Run #1 is unchanged.",
    ],
    limitations: [
      "The default demo uses the simulator's hardware model. It is not a physical server.",
      "Redfish fixtures are hand-written in the shape of DMTF mockups. Real BMCs populate different properties, and vendor OEM sections differ.",
      "Disk health and kernel logs usually need root. Without it the Linux collector reports UNSUPPORTED, which forces manual review.",
      "No burn-in, memory stress or firmware compliance testing is run. Those are deliberately out of scope for safety.",
    ],
  },
  "rack-lifecycle": {
    relevance: [
      "Accurate rack, cable and power records decide whether a remote engineer can trust a work order.",
      "Two PSUs on two PDUs is not redundancy if both PDUs trace back to one UPS.",
      "Spares that are reserved twice or consumed without a record cause stock-outs during the next failure.",
      "Failed parts need a traceable return linked to evidence, the incident and the replacement serial.",
    ],
    workflow: [
      { t: "Locate", d: "Device in rack elevation" },
      { t: "Evidence", d: "BMC, SEL, PDU outlet" },
      { t: "Compatible spare", d: "Compatibility list" },
      { t: "Reserve", d: "Available ↓, on-hand ="  },
      { t: "Consume", d: "Atomic ledger write" },
      { t: "Return", d: "RMA record, no vendor call" },
      { t: "Re-check", d: "Health verification" },
    ],
    arch: {
      services: ["services/topology.py", "services/inventory.py", "services/incidents.py", "components/rack/RackElevation.tsx"],
      tables: ["racks", "devices", "device_interfaces", "cable_connections", "power_inputs", "pdu_outlets", "power_feeds", "assets", "spare_stock", "reservations", "inventory_transactions", "return_records", "audit_events"],
      external: "Optional: read-only NetBox JSON import",
    },
    script: [
      "Start the demo. The modeled BMC reports PSU2 Critical on lab-srv-04, and an incident opens.",
      "Open the device: PSU2 rear view, power inputs, and the feed/upstream analysis.",
      "Review the evidence. The outlet is ON and neighbouring loads are healthy, so the PSU is at fault.",
      "Reserve NL-PSU-800P (NL-PSU-550S is flagged incompatible), then consume it with the replacement serial.",
      "Open the return record, re-run the health check, resolve, and walk the audit trail.",
    ],
    limitations: [
      "All topology is a documentation model (Modeled lab topology), not discovered from hardware or LLDP.",
      "Power analysis is a documentation model, not an electrical design certification. Loads are estimates.",
      "Physical replacement is simulated. The workflow records the swap; it cannot prove the work was done.",
      "The return workflow records references entered by the operator. It never contacts a vendor.",
      "Single-user SQLite: stock serialization relies on BEGIN IMMEDIATE, which is appropriate locally but not for a multi-site service.",
    ],
  },
};

const COMMANDS = [
  { label: "Backend (API + job runner)", cmd: "cd backend && uv sync && uv run alembic upgrade head && uv run python -m app.seed && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000" },
  { label: "Frontend", cmd: "cd frontend && npm ci && npm run dev" },
];

function Sec({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22 }}
      className="panel p-5" style={{ breakInside: "avoid" }} aria-labelledby={`sec-${n}`}>
      <h2 id={`sec-${n}`} className="mb-3 flex items-center gap-2.5 text-[15px] font-semibold text-ink">
        <span className="mono grid h-6 w-6 place-items-center rounded-md bg-nav text-[11px] font-bold text-accent-300" aria-hidden>{n}</span>{title}
      </h2>
      {children}
    </motion.section>
  );
}

function WorkflowDiagram({ steps }: { steps: Detail["workflow"] }) {
  return (
    <ol className="flex flex-wrap items-stretch gap-y-3" aria-label="Workflow steps">
      {steps.map((s, i) => (
        <li key={s.t} className="flex items-center">
          <motion.div initial={{ opacity: 0, scale: 0.94 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.08, duration: 0.2 }}
            className="w-[124px] rounded-xl border border-line bg-white px-3 py-2.5 shadow-panel">
            <div className="mono text-[10px] text-ink-3">STEP {i + 1}</div>
            <div className="text-[13px] font-semibold text-ink">{s.t}</div>
            <div className="text-[11.5px] leading-snug text-ink-2">{s.d}</div>
          </motion.div>
          {i < steps.length - 1 && (
            <motion.span initial={{ opacity: 0, x: -4 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.08 + 0.1 }} className="px-1.5 text-accent" aria-hidden>
              <ArrowRight className="h-4 w-4" />
            </motion.span>
          )}
        </li>
      ))}
    </ol>
  );
}

function Box({ title, sub, items, tone = "default" }: { title: string; sub?: string; items?: string[]; tone?: "default" | "dark" | "accent" }) {
  return (
    <div className={clsx("rounded-xl border p-3", tone === "dark" ? "border-nav-line bg-nav text-nav-text" : tone === "accent" ? "border-accent/30 bg-accent-50/60" : "border-line bg-white")}>
      <div className={clsx("text-[12.5px] font-semibold", tone === "dark" ? "text-white" : "text-ink")}>{title}</div>
      {sub && <div className={clsx("text-[11px]", tone === "dark" ? "text-nav-muted" : "text-ink-2")}>{sub}</div>}
      {items && <ul className="mt-1.5 space-y-0.5">{items.map((x) => <li key={x} className={clsx("mono text-[10.5px]", tone === "dark" ? "text-nav-text" : "text-ink")}>{x}</li>)}</ul>}
    </div>
  );
}

function Architecture({ d }: { d: Detail }) {
  const arrow = <div className="flex items-center justify-center py-1 text-ink-3 lg:px-1 lg:py-0" aria-hidden><span className="lg:hidden">↓</span><span className="hidden lg:inline">⇄</span></div>;
  return (
    <div>
      <div className="grid grid-cols-1 items-stretch gap-0 lg:grid-cols-[1fr_auto_1fr_auto_1.3fr_auto_1fr]">
        <Box title="React UI" sub="Vite · TanStack Query · SSE client" items={["EventSource + Last-Event-ID", "query invalidation per topic"]} />
        {arrow}
        <Box title="FastAPI routers" sub="Typed schemas · OpenAPI · error envelope" items={["Idempotency-Key", "public-preview guard"]} tone="dark" />
        {arrow}
        <Box title="Domain services" sub="Rules enforced server-side" items={d.arch.services} tone="accent" />
        {arrow}
        <Box title="SQLite (Alembic)" sub="WAL · FK · constraints" items={d.arch.tables} />
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Box title="Job runner (asyncio, 1 s tick)" sub="Simulation probes · acceptance checks · live-lab probes" />
        <Box title="Persisted event stream" sub="stream_events → /api/events (SSE) with replay on reconnect" />
      </div>
      <p className="mt-2 text-[12px] text-ink-2">{d.arch.external}</p>
      <p className="sr-only">Data flows from the React UI to FastAPI routers, which call domain services that read and write SQLite. A background job runner advances simulations and runs checks; changes are published as server-sent events back to the UI.</p>
    </div>
  );
}

function ResultsSection({ slug }: { slug: string }) {
  const r = useProjectResults(slug);
  if (slug === "incident-recovery") return <MetricsPanel printable />;
  if (r.isLoading) return <LoadingBlock rows={4} />;
  if (r.error) return <ErrorState error={r.error} retry={() => r.refetch()} />;
  const data = r.data ?? {};
  if (slug === "server-acceptance") {
    const by = (data.by_source ?? {}) as Record<string, { runs: number; PASS: number; FAIL: number; MANUAL_REVIEW: number; items: any[] }>;
    const srcs = Object.keys(by);
    if (!srcs.length) return <Empty title="No results collected yet">Run the acceptance demo or start a run from the acceptance queue. No numbers are shown until runs exist.</Empty>;
    return (
      <div className="space-y-4">
        {srcs.map((s) => (
          <div key={s}>
            <div className="mb-2 flex flex-wrap items-center gap-2"><SourceBadge source={s as SourceType} /><span className="text-[12.5px] text-ink-2">{by[s].runs} completed run(s)</span></div>
            <div className="mb-2 grid grid-cols-3 gap-2">
              {(["PASS", "FAIL", "MANUAL_REVIEW"] as const).map((k) => (
                <div key={k} className="rounded-lg border border-line p-2.5"><ResultBadge result={k} /><div className="mono mt-1 text-[18px] font-semibold">{by[s][k]}</div></div>
              ))}
            </div>
            <ul className="divide-y divide-line-soft rounded-lg border border-line">
              {by[s].items.map((x) => (
                <li key={x.id}>
                  <Link to={`/acceptance/${x.intake_id}?run=${x.id}`} className="flex flex-wrap items-center gap-2 px-3 py-2 text-[12.5px] hover:bg-canvas">
                    <span className="mono font-medium">{x.display_id}</span><span className="mono text-ink-2">{x.hostname} #{x.run_number}</span>
                    <ResultBadge result={x.disposition} /><span className="mono ml-auto text-ink-3">{fmtDateTime(x.completed_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    );
  }
  const issues = (data.cable_issues ?? []) as { cable_id: number; code: string; severity: string; message: string }[];
  const power = (data.power?.issues ?? []) as { device: string; code: string; severity: string; message: string }[];
  const res = (data.reservations ?? []) as { status: string; origin: string }[];
  const rets = (data.returns ?? []) as { origin: string }[];
  const count = (xs: { origin: string }[], sim: boolean) => xs.filter((x) => (x.origin === "simulation") === sim).length;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-4">
        {[
          ["Cable documentation defects", issues.length, "Modeled lab topology"],
          ["Power documentation findings", power.length, "Modeled lab topology"],
          ["Reservations", `${count(res, true)} sim · ${count(res, false)} other`, "By record origin"],
          ["Return records", `${count(rets, true)} sim · ${count(rets, false)} other`, "By record origin"],
        ].map(([l, v, s]) => (
          <div key={l as string} className="rounded-lg border border-line p-3">
            <div className="eyebrow">{l}</div><div className="mono mt-1 text-[18px] font-semibold">{v}</div><div className="text-[11px] text-ink-2">{s}</div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <div className="eyebrow mb-1">Cable audit (modeled)</div>
          {issues.length === 0 ? <p className="text-[12.5px] text-ink-2">No open cable defects.</p> : (
            <ul className="space-y-1 text-[12.5px]">{issues.map((i, k) => <li key={k} className="flex gap-2"><Pill className={i.severity === "critical" ? "border-crit/30 bg-crit-50 text-crit" : "border-warn/30 bg-warn-50 text-warn"}>{i.code}</Pill><span>{i.message}</span></li>)}</ul>
          )}
        </div>
        <div>
          <div className="eyebrow mb-1">Power findings (modeled)</div>
          {power.length === 0 ? <p className="text-[12.5px] text-ink-2">No power findings.</p> : (
            <ul className="space-y-1 text-[12.5px]">{power.map((i, k) => <li key={k} className="flex gap-2"><Pill className={i.severity === "critical" ? "border-crit/30 bg-crit-50 text-crit" : "border-warn/30 bg-warn-50 text-warn"}>{i.code}</Pill><span><span className="mono">{i.device}</span>: {i.message}</span></li>)}</ul>
          )}
        </div>
      </div>
      {res.length === 0 && rets.length === 0 && <p className="text-[12.5px] text-ink-2">No reservations or returns collected yet. Run the component replacement demo to produce them.</p>}
    </div>
  );
}

function Notes({ slug }: { slug: string }) {
  const p = useProfile();
  const saved = p.data?.project_notes?.[slug] ?? { candidate_contribution: "", lessons_learned: "" };
  const [c, setC] = useState("");
  const [l, setL] = useState("");
  useEffect(() => { setC(saved.candidate_contribution ?? ""); setL(saved.lessons_learned ?? ""); }, [saved.candidate_contribution, saved.lessons_learned]);
  const dirty = c !== (saved.candidate_contribution ?? "") || l !== (saved.lessons_learned ?? "");
  const save = useAction(() => put(`/projects/${slug}/notes`, { candidate_contribution: c, lessons_learned: l }), { success: "Notes saved" });
  const placeholder = "Write in your own words. This portfolio does not generate personal reflections.";
  const block = (n: number, title: string, id: string, v: string, set: (s: string) => void) => (
    <Sec n={n} title={title}>
      <label htmlFor={id} className="sr-only">{title}</label>
      <textarea id={id} className="input no-print min-h-[120px]" rows={5} value={v} onChange={(e) => set(e.target.value)} placeholder={placeholder} maxLength={8000} />
      <div className="print-only whitespace-pre-wrap text-[13px] leading-relaxed">{v.trim() || "[Not yet written]"}</div>
      {n === 9 && (
        <div className="no-print mt-3 flex items-center gap-2">
          <button className="btn-primary" disabled={!dirty || save.isPending} onClick={() => save.mutate()}><Save className="h-4 w-4" aria-hidden />Save notes</button>
          <span className="text-[12px] text-ink-2">{dirty ? "Unsaved changes" : "Saved to the database"}</span>
        </div>
      )}
    </Sec>
  );
  return <>{block(8, "Candidate contribution", `contrib-${slug}`, c, setC)}{block(9, "Lessons learned", `lessons-${slug}`, l, setL)}</>;
}

export function CaseStudy() {
  const { slug = "" } = useParams();
  const nav = useNavigate();
  const project = PROJECTS.find((p) => p.slug === slug);
  const d = DETAILS[slug];
  const start = useAction((key: string) => post<any>(`/demos/${key}/start`), {
    success: "Demo started. Follow the guide at the bottom of the screen.",
    onSuccess: (r) => { const step = r.steps?.find((s: any) => !s.done && s.route); nav(step?.route ?? "/"); },
  });
  if (!project || !d) return <div className="panel"><Empty title="Unknown case study" action={<Link to="/" className="btn-primary">Back to portfolio</Link>}>Choose one of the three projects.</Empty></div>;
  const Icon = project.icon;

  return (
    <div className="space-y-4">
      <header className="panel relative overflow-hidden p-5 md:p-6">
        <div className="grid-bg absolute inset-0 opacity-50" aria-hidden />
        <div className="relative flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="flex items-start gap-3">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-nav text-accent-300"><Icon className="h-5 w-5" aria-hidden /></span>
            <div>
              <div className="eyebrow">Case study · Project {project.n}</div>
              <h1 className="text-[22px] font-semibold leading-tight text-ink md:text-[26px]">{project.title}</h1>
              <div className="mt-1.5 flex flex-wrap gap-2">
                <Pill className="border-accent/30 bg-accent-50 text-accent-700"><ShieldCheck className="h-3 w-3" aria-hidden />Independent interview lab · synthetic data</Pill>
              </div>
            </div>
          </div>
          <div className="no-print flex flex-wrap gap-2">
            <button className="btn-primary" onClick={() => start.mutate(project.demo)} disabled={start.isPending}><PlayCircle className="h-4 w-4" aria-hidden />Run demonstration</button>
            <button className="btn-secondary" onClick={() => window.print()}><Printer className="h-4 w-4" aria-hidden />Print case study</button>
          </div>
        </div>
      </header>

      <Sec n={1} title="Problem"><p className="max-w-3xl text-[13.5px] leading-relaxed text-ink">{project.problem}</p></Sec>
      <Sec n={2} title="Relevance to data center operations">
        <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">{d.relevance.map((r) => <li key={r} className="flex gap-2 text-[13px] leading-relaxed text-ink"><Check className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden />{r}</li>)}</ul>
      </Sec>
      <Sec n={3} title="Implemented workflow"><WorkflowDiagram steps={d.workflow} /></Sec>
      <Sec n={4} title="Architecture"><Architecture d={d} /></Sec>
      <Sec n={5} title="Demonstration">
        <ol className="space-y-1.5">{d.script.map((s, i) => <li key={s} className="flex gap-2.5 text-[13px] text-ink"><span className="mono w-5 shrink-0 text-right text-ink-3">{i + 1}.</span>{s}</li>)}</ol>
        <div className="no-print mt-3 flex flex-wrap gap-2">
          <button className="btn-primary btn-sm" onClick={() => start.mutate(project.demo)} disabled={start.isPending}><PlayCircle className="h-3.5 w-3.5" aria-hidden />Start guided demo</button>
          <Link to="/demo" className="btn-ghost btn-sm">All demonstrations →</Link>
        </div>
      </Sec>
      <Sec n={6} title="Collected results">
        <p className="mb-3 text-[12.5px] text-ink-2">Computed live from stored records and separated by source. Nothing here is estimated or invented.</p>
        <ResultsSection slug={slug} />
      </Sec>
      <Sec n={7} title="Limitations">
        <ul className="space-y-1.5">{d.limitations.map((l) => <li key={l} className="flex gap-2 text-[13px] leading-relaxed text-ink"><span className="mt-[8px] h-1 w-1 shrink-0 rounded-full bg-warn" aria-hidden />{l}</li>)}</ul>
      </Sec>
      <Notes slug={slug} />
      <Sec n={10} title="Reproduction instructions">
        <div className="space-y-3">
          {COMMANDS.map((c) => (
            <div key={c.label}>
              <div className="mb-1 flex items-center justify-between gap-2"><span className="eyebrow">{c.label}</span><span className="no-print"><CopyButton text={c.cmd} label="Copy command" /></span></div>
              <pre className="pre">{c.cmd}</pre>
            </div>
          ))}
          <p className="text-[13px] text-ink">Then open <span className="mono">http://localhost:5173/demo</span> and start <b>{project.title}</b>, or open this page at <span className="mono">/projects/{slug}</span>.</p>
        </div>
      </Sec>
      <p className="pb-2 text-center text-[11.5px] text-ink-2">RackOps Lab · Independent interview lab · Not affiliated with any employer · All data is synthetic unless labeled LOCAL LAB.</p>
    </div>
  );
}
