import clsx from "clsx";
import { motion } from "framer-motion";
import { AlertOctagon, BookOpen, CheckCircle2, FlaskConical, GitBranch, Printer, RotateCcw, Search, ShieldCheck, Wrench } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { post } from "@/api/client";
import { useAction, useRunbooks } from "@/api/hooks";
import { Pill } from "@/components/ui/Badges";
import { Empty, ErrorState, LoadingBlock, PageHeader } from "@/components/ui/Primitives";

const PROJECT_NAMES: Record<string, string> = {
  "incident-recovery": "Incident Detection & Recovery",
  "server-acceptance": "Server Intake & Acceptance",
  "rack-lifecycle": "Rack, Cabling & Asset Lifecycle",
};

interface RunbookStep { step: string; collector: string | null; why: string }
interface Runbook {
  slug: string; title: string; project: string; symptom: string; scenario_keys: string[]; version: string;
  sections: {
    initial_checks: string[]; investigation: RunbookStep[]; decision_points: string[]; corrective_action: string[];
    verification: string[]; escalation: string[]; rollback: string[];
  };
}

function Section({ n, title, icon, children }: { n: number; title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <section className="border-t border-line-soft pt-4 first:border-t-0 first:pt-0" style={{ breakInside: "avoid" }}>
      <h3 className="mb-2 flex items-center gap-2 text-[13.5px] font-semibold text-ink">
        <span className="grid h-6 w-6 place-items-center rounded-md bg-nav text-[11px] font-bold text-accent-300" aria-hidden>{n}</span>
        <span className="text-ink-3" aria-hidden>{icon}</span>
        {title}
      </h3>
      <div className="pl-8">{children}</div>
    </section>
  );
}

function Bullets({ items }: { items: string[] }) {
  if (!items?.length) return <p className="text-[12.5px] text-ink-2">None documented.</p>;
  return (
    <ul className="space-y-1.5">
      {items.map((t) => (
        <li key={t} className="flex gap-2 text-[13px] leading-relaxed text-ink">
          <span className="mt-[8px] h-1 w-1 shrink-0 rounded-full bg-accent" aria-hidden />{t}
        </li>
      ))}
    </ul>
  );
}

export function Runbooks() {
  const { slug } = useParams();
  const nav = useNavigate();
  const q = useRunbooks();
  const drill = useAction((key: string) => post(`/scenarios/${key}/start`), {
    success: "Drill started: baseline probes running",
    onSuccess: () => nav("/"),
  });

  if (q.isLoading) return <LoadingBlock rows={10} label="Loading runbooks" />;
  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const books = (q.data ?? []) as Runbook[];
  const rb = books.find((b) => b.slug === slug) ?? books[0];
  const groups = Object.keys(PROJECT_NAMES).map((p) => ({ p, items: books.filter((b) => b.project === p) })).filter((g) => g.items.length);

  return (
    <div>
      <div className="no-print">
        <PageHeader title="Runbooks"
          actions={rb && <button className="btn-secondary" onClick={() => window.print()}><Printer className="h-4 w-4" aria-hidden />Print runbook</button>}>
          Standard procedures for common faults and hardware work.
        </PageHeader>
      </div>
      {books.length === 0 ? <div className="panel"><Empty title="No runbooks seeded" icon={<BookOpen className="h-5 w-5" />}>Run the seed command to load the runbooks.</Empty></div> : (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
          <nav aria-label="Runbook list" className="no-print panel h-max overflow-hidden lg:sticky lg:top-20">
            {groups.map((g) => (
              <div key={g.p} className="border-b border-line-soft last:border-b-0">
                <div className="eyebrow px-4 pb-1 pt-3">{PROJECT_NAMES[g.p]}</div>
                <ul className="px-2 pb-2">
                  {g.items.map((b) => {
                    const active = b.slug === rb?.slug;
                    return (
                      <li key={b.slug}>
                        <Link to={`/runbooks/${b.slug}`} aria-current={active ? "page" : undefined}
                          className={clsx("relative block rounded-lg px-2.5 py-2 text-[13px] transition-colors duration-150",
                            active ? "bg-accent-50 font-medium text-accent-700" : "text-ink hover:bg-canvas")}>
                          {active && <motion.span layoutId="rb-active" className="absolute inset-y-1.5 left-0 w-[3px] rounded-r bg-accent" transition={{ duration: 0.2 }} />}
                          <span className="block truncate">{b.title}</span>
                          <span className="mono text-[10.5px] text-ink-3">v{b.version}{b.scenario_keys.length ? ` · ${b.scenario_keys.join(", ")}` : ""}</span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </nav>

          {rb && (
            <motion.article key={rb.slug} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }} className="panel min-w-0">
              <header className="border-b border-line-soft p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <Pill className="border-line bg-canvas text-ink-2">{PROJECT_NAMES[rb.project] ?? rb.project}</Pill>
                  <Pill className="border-accent/30 bg-accent-50 text-accent-700">Version {rb.version}</Pill>
                  <span className="mono text-[11px] text-ink-3">{rb.slug}</span>
                </div>
                <h2 className="mt-2 text-[20px] font-semibold leading-tight text-ink">{rb.title}</h2>
                <div className="mt-3 rounded-lg border border-warn/25 bg-warn-50/60 px-3 py-2">
                  <div className="eyebrow text-warn">Symptom</div>
                  <p className="text-[13px] text-ink">{rb.symptom}</p>
                </div>
                {rb.scenario_keys.length > 0 && (
                  <div className="no-print mt-3 flex flex-wrap items-center gap-2">
                    <span className="text-[12px] text-ink-2">Linked simulated scenario{rb.scenario_keys.length > 1 ? "s" : ""}:</span>
                    {rb.scenario_keys.map((k) => (
                      <button key={k} className="btn-primary btn-sm" disabled={drill.isPending} onClick={() => drill.mutate(k)}>
                        <FlaskConical className="h-3.5 w-3.5" aria-hidden />Run <span className="mono">{k}</span> as a drill
                      </button>
                    ))}
                  </div>
                )}
              </header>
              <div className="space-y-4 p-5">
                <Section n={1} title="Initial checks" icon={<Search className="h-4 w-4" />}><Bullets items={rb.sections.initial_checks} /></Section>
                <Section n={2} title="Investigation sequence" icon={<GitBranch className="h-4 w-4" />}>
                  <ol className="space-y-2.5">
                    {rb.sections.investigation.map((s, i) => (
                      <li key={i} className="flex gap-3">
                        <span className="mono mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border border-line-strong text-[10px] font-semibold text-ink-2">{i + 1}</span>
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-[13px] font-medium text-ink">{s.step}</span>
                            {s.collector && <span className="mono rounded-md border border-accent/30 bg-accent-50 px-1.5 text-[10.5px] text-accent-700">{s.collector}</span>}
                          </div>
                          <p className="text-[12.5px] text-ink-2">{s.why}</p>
                        </div>
                      </li>
                    ))}
                  </ol>
                </Section>
                <Section n={3} title="Decision points" icon={<GitBranch className="h-4 w-4" />}><Bullets items={rb.sections.decision_points} /></Section>
                <Section n={4} title="Corrective action" icon={<Wrench className="h-4 w-4" />}><Bullets items={rb.sections.corrective_action} /></Section>
                <Section n={5} title="Verification" icon={<ShieldCheck className="h-4 w-4" />}>
                  <ul className="space-y-1.5">
                    {rb.sections.verification.map((t) => (
                      <li key={t} className="flex gap-2 text-[13px] text-ink"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-ok" aria-hidden />{t}</li>
                    ))}
                  </ul>
                </Section>
                <Section n={6} title="Escalation criteria" icon={<AlertOctagon className="h-4 w-4" />}><Bullets items={rb.sections.escalation} /></Section>
                <Section n={7} title="Rollback and recovery considerations" icon={<RotateCcw className="h-4 w-4" />}><Bullets items={rb.sections.rollback} /></Section>
              </div>
              <footer className="border-t border-line-soft px-5 py-3 text-[11.5px] text-ink-2">
                RackOps Lab runbook · Procedures are written for the modeled North Lab and must be adapted to a real facility's change process.
              </footer>
            </motion.article>
          )}
        </div>
      )}
    </div>
  );
}
