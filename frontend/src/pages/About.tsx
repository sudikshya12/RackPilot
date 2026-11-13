import { ArrowRight, ClipboardCheck, FileCode2, Network, Siren } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { post } from "@/api/client";
import { useAction, useProfile } from "@/api/hooks";
import { PageHeader, Panel } from "@/components/ui/Primitives";

export const PROJECTS = [
  {
    slug: "incident-recovery", n: 1, title: "Incident Detection & Recovery", icon: Siren, demo: "restore-service",
    problem: "Detect a failure, collect evidence, reject a plausible wrong fix, and prove recovery before resolving.",
    shows: ["Deterministic fault injection and detection", "Evidence kept separate from diagnosis", "Verification gate before resolution", "MTTR: detection to verified recovery"],
  },
  {
    slug: "server-acceptance", n: 2, title: "Server Intake & Acceptance", icon: ClipboardCheck, demo: "acceptance-retest",
    problem: "Validate a new server against its build sheet before handoff to provisioning.",
    shows: ["Modular checks with six result states", "Immutable runs and re-test comparison", "Printable report and JSON export", "Read-only Redfish adapter"],
  },
  {
    slug: "rack-lifecycle", n: 3, title: "Rack, Cabling & Asset Lifecycle", icon: Network, demo: "replace-component",
    problem: "Keep rack, cabling, power and spare-part records accurate through a repair.",
    shows: ["Rack elevation and cable trace", "Power independence analysis", "Transactional reserve and consume", "Returns with a full audit trail"],
  },
];

export function About() {
  const profile = useProfile();
  const nav = useNavigate();
  const start = useAction((key: string) => post<any>(`/demos/${key}/start`), {
    onSuccess: (r) => nav(r.steps?.find((s: any) => !s.done && s.route)?.route ?? "/"),
  });
  return (
    <div className="space-y-5">
      <PageHeader title="About & Documentation">
        RackOps Lab is an independent lab application for data center operations workflows. It is not affiliated with any employer, and all lab data is synthetic.
      </PageHeader>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <Panel title="Projects" bodyClass="divide-y divide-line-soft">
          {PROJECTS.map((p) => (
            <div key={p.slug} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-nav text-accent-300"><p.icon className="h-4 w-4" aria-hidden /></span>
              <div className="min-w-0 flex-1">
                <h2 className="text-[14px] font-semibold text-ink">{p.n}. {p.title}</h2>
                <p className="mt-0.5 text-[12.5px] text-ink-2">{p.problem}</p>
                <p className="mt-1.5 text-[12px] text-ink-3">{p.shows.join(" · ")}</p>
              </div>
              <div className="flex shrink-0 gap-2">
                <Link to={`/projects/${p.slug}`} className="btn-secondary btn-sm">Case study</Link>
                <button className="btn-ghost btn-sm" onClick={() => start.mutate(p.demo)} disabled={start.isPending}>Run demo</button>
              </div>
            </div>
          ))}
        </Panel>

        <div className="space-y-5">
          <Panel title="Author">
            <div className="text-[14px] font-medium text-ink">{profile.data?.name}</div>
            <div className="text-[12.5px] text-ink-2">{profile.data?.headline}</div>
            {profile.data?.summary && <p className="mt-2 text-[12.5px] text-ink-2">{profile.data.summary}</p>}
            {(profile.data?.links ?? []).filter((l: { url: string }) => l.url).map((l: { label: string; url: string }) => (
              <a key={l.url} href={l.url} target="_blank" rel="noreferrer" className="mt-1 block text-[12.5px] text-accent-700 hover:underline">{l.label}</a>
            ))}
            <Link to="/settings" className="mt-3 inline-block text-[12px] text-ink-2 hover:text-ink">Edit in Settings</Link>
          </Panel>

          <Panel title="Data sources">
            <dl className="space-y-2 text-[12.5px]">
              <div><dt className="font-medium text-ink">Simulated</dt><dd className="text-ink-2">Deterministic drills built from fixed sequences. This is the default for all demos.</dd></div>
              <div><dt className="font-medium text-ink">Local lab</dt><dd className="text-ink-2">Opt-in real observations: the live-lab target, uploaded Linux collector output, or a configured Redfish BMC.</dd></div>
              <div><dt className="font-medium text-ink">Imported sample</dt><dd className="text-ink-2">Bundled or uploaded samples, such as an Alertmanager payload, Redfish fixtures, or a NetBox export.</dd></div>
            </dl>
            <p className="mt-2 text-[12px] text-ink-3">Sources are never combined in one aggregate. The rack, cabling and power model is synthetic.</p>
          </Panel>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Panel title="How it is built">
          <ul className="space-y-1.5 text-[12.5px] text-ink-2">
            <li><b className="font-medium text-ink">Backend:</b> FastAPI, SQLAlchemy 2, Alembic, SQLite (WAL)</li>
            <li><b className="font-medium text-ink">Job runner:</b> backend asyncio loop for simulation, acceptance checks and live probes</li>
            <li><b className="font-medium text-ink">Events:</b> persisted server-sent events with replay on reconnect</li>
            <li><b className="font-medium text-ink">Frontend:</b> React, TypeScript, Vite, Tailwind, TanStack Query</li>
            <li><b className="font-medium text-ink">Integrity:</b> ledger-derived stock, idempotency keys, verification gate, immutable runs</li>
            <li><b className="font-medium text-ink">Tests:</b> pytest workflow suite, Playwright demo journeys and responsive checks</li>
          </ul>
        </Panel>
        <Panel title="Documentation" bodyClass="divide-y divide-line-soft">
          {[
            ["/runbooks", "Runbooks", "Operational procedures"],
            ["/demo", "Demonstrations", "Guided walkthroughs and simulation reset"],
          ].map(([to, t, s]) => (
            <Link key={to} to={to} className="flex items-center gap-3 px-4 py-3 hover:bg-canvas">
              <div className="min-w-0 flex-1"><div className="text-[13px] font-medium">{t}</div><div className="text-[12px] text-ink-2">{s}</div></div>
              <ArrowRight className="h-4 w-4 text-ink-3" aria-hidden />
            </Link>
          ))}
          <a href="/api/docs" target="_blank" rel="noreferrer" className="flex items-center gap-3 px-4 py-3 hover:bg-canvas">
            <FileCode2 className="h-4 w-4 text-ink-3" aria-hidden />
            <div className="min-w-0 flex-1"><div className="text-[13px] font-medium">API reference</div><div className="text-[12px] text-ink-2">OpenAPI at /api/docs</div></div>
            <ArrowRight className="h-4 w-4 text-ink-3" aria-hidden />
          </a>
          <div className="px-4 py-3 text-[12px] text-ink-2">The architecture, data dictionary, simulation model and limitations are in <span className="mono">docs/</span> in the repository.</div>
        </Panel>
      </div>
    </div>
  );
}
