import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Check, ChevronDown, FileJson, FileText, GitCompareArrows, Loader2, Play, Upload, Wrench } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, post } from "@/api/client";
import { useAction, useCollectorsAcc, useIntake, useRun } from "@/api/hooks";
import type { CheckResultRow, Intake, RunDetail } from "@/api/types";
import { Pill, ResultBadge, SourceBadge } from "@/components/ui/Badges";
import { CopyButton, Empty, ErrorState, KV, LoadingBlock, Modal, Panel } from "@/components/ui/Primitives";
import { useToast } from "@/components/ui/Toast";
import { fmtDateTime, fmtTime } from "@/lib/format";
import { IntakeStatus } from "./AcceptanceQueue";

const markDemo = (step: string) => post(`/demos/acceptance-retest/view/${step}`).catch(() => undefined);

function ExpectedCard({ x }: { x: Intake }) {
  const e = x.expected;
  return (
    <Panel title="Expected configuration" sub="Recorded at intake, before measuring">
      <dl className="divide-y divide-line-soft">
        <KV k="CPU" v={`${e.cpu_count} × ${e.cpu_model}`} />
        <KV k="Memory" v={`${e.memory_gib} GiB`} mono />
        <KV k="Storage" v={e.storage.map((s) => `${s.count} × ${s.size_gb} GB ${s.type}`).join(", ")} mono />
        <KV k="NICs" v={`${e.nic_count} interfaces`} />
        <KV k="Data link" v={`${e.data_link_speed_mbps} Mb/s`} mono />
        <KV k="Rack position" v={x.intended_rack ? `${x.intended_rack} U${x.intended_position_u}` : "Not decided"} mono />
        <KV k="Profile" v={`${x.profile.key} v${x.profile.version}`} mono />
      </dl>
    </Panel>
  );
}

function ResultRow({ r, review, onReview }: { r: CheckResultRow; review?: { decision: string; note: string; by: string }; onReview?: () => void }) {
  const [open, setOpen] = useState(false);
  const conclusive = r.result === "PASS" || r.result === "FAIL";
  return (
    <>
      <motion.tr initial={{ opacity: 0, backgroundColor: "rgba(8,127,140,0.10)" }} animate={{ opacity: 1, backgroundColor: "rgba(255,255,255,0)" }} transition={{ duration: 0.5 }}
        className={clsx(r.result === "FAIL" && r.required && "bg-crit-50/40")}>
        <td>
          <button className="flex items-center gap-1.5 text-left font-medium text-ink" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
            <ChevronDown className={clsx("h-3.5 w-3.5 shrink-0 text-ink-3 transition-transform", open && "rotate-180")} aria-hidden />{r.check_name}
          </button>
          <span className="mono ml-5 text-[10.5px] text-ink-3">{r.check_key} v{r.check_version}</span>
        </td>
        <td>{r.required ? <span className="text-[12px] font-medium">Required</span> : <span className="text-[12px] text-ink-2">Optional</span>}</td>
        <td className="mono">{r.expected_value ?? "—"}</td>
        <td className={clsx("mono", r.result === "FAIL" && "font-semibold text-crit")}>{r.observed_value ?? "Not collected"}</td>
        <td className="mono text-ink-2">{r.unit ?? ""}</td>
        <td><ResultBadge result={r.result} />{review && <div className="mt-0.5 text-[10.5px] text-ink-2">reviewed: {review.decision}</div>}</td>
        <td className="text-right">{!conclusive && r.required && !review && onReview && <button className="btn-secondary btn-sm" onClick={onReview}>Review</button>}</td>
      </motion.tr>
      {open && (
        <tr className="bg-canvas/60">
          <td colSpan={7} className="px-4 py-3">
            {r.detail && <p className="mb-2 text-[12.5px] text-ink">{r.detail}</p>}
            {review && <p className="mb-2 rounded-lg bg-warn-50 px-2.5 py-1.5 text-[12px]">Manual review by <b>{review.by}</b>: {review.decision}. {review.note}</p>}
            {r.evidence ? (
              <div>
                <div className="mb-1 flex items-center justify-between gap-2"><code className="mono text-[11.5px] text-ink-2">$ {r.evidence.command}</code><CopyButton text={r.evidence.output} /></div>
                <pre className="pre max-h-52">{r.evidence.output}</pre>
                <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-ink-2"><SourceBadge source={r.evidence.source_type} /><span className="mono">{r.evidence.display_id}</span><span className="mono">{fmtDateTime(r.evidence.collected_at)}</span><span className="italic">{r.evidence.limitations}</span></div>
              </div>
            ) : <p className="text-[12px] text-ink-2">No evidence output for this check.</p>}
          </td>
        </tr>
      )}
    </>
  );
}

function RunView({ runId }: { runId: number }) {
  const q = useRun(runId);
  const toast = useToast();
  const [rev, setRev] = useState<CheckResultRow | null>(null);
  const [decision, setDecision] = useState<"accept" | "reject">("accept");
  const [note, setNote] = useState("");
  const review = useAction(() => post(`/acceptance/runs/${runId}/manual-review`, { check_key: rev!.check_key, decision, note }), { success: "Manual review recorded. The original result is unchanged.", onSuccess: () => { setRev(null); setNote(""); } });
  const marked = useRef(false);
  useEffect(() => {
    if (q.data?.status === "completed" && q.data.disposition === "FAIL" && !marked.current) { marked.current = true; markDemo("failures"); }
  }, [q.data]);
  useEffect(() => { if (q.data && q.data.status !== "completed") { const t = setInterval(() => q.refetch(), 900); return () => clearInterval(t); } }, [q.data?.status]); // eslint-disable-line
  if (q.isLoading) return <LoadingBlock rows={8} />;
  if (q.error || !q.data) return <ErrorState error={q.error} />;
  const r: RunDetail = q.data;
  const running = r.status !== "completed";
  const pct = Math.round((r.checks_done / Math.max(r.checks_total, 1)) * 100);
  const req = r.results.filter((x) => x.required);
  return (
    <Panel title={<span className="flex items-center gap-2">Run #{r.run_number} <span className="mono text-[12px] font-normal text-ink-2">{r.display_id}</span></span>}
      sub={<>Collector <span className="mono">{r.collector}</span> · operator {r.operator} · {fmtDateTime(r.started_at ?? r.created_at)}</>}
      actions={!running && <>
        <Link to={`/acceptance/runs/${r.id}/report`} className="btn-secondary btn-sm"><FileText className="h-3.5 w-3.5" aria-hidden />Report</Link>
        <a href={`/api/acceptance/runs/${r.id}/report.json`} download className="btn-ghost btn-sm"><FileJson className="h-3.5 w-3.5" aria-hidden />JSON</a>
      </>} bodyClass="">
      <div className="flex flex-col gap-4 border-b border-line-soft p-4 md:flex-row md:items-center">
        <div className="flex items-center gap-3">
          <AnimatePresence mode="wait">
            <motion.div key={running ? "run" : r.disposition} initial={{ scale: 0.85, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: "spring", stiffness: 380, damping: 24 }}>
              {running ? <Pill className="border-accent/30 bg-accent-50 px-3 py-1 text-[13px] text-accent-700"><Loader2 className="h-4 w-4 animate-spin" aria-hidden />Running {r.checks_done}/{r.checks_total}</Pill> : <ResultBadge result={r.disposition} size="lg" />}
            </motion.div>
          </AnimatePresence>
          {!running && r.effective_disposition !== r.disposition && <span className="text-[12px] text-ink-2">After manual review: <ResultBadge result={r.effective_disposition} /></span>}
        </div>
        <div className="flex-1">
          <div className="h-1.5 overflow-hidden rounded-full bg-line-soft" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Checks completed">
            <motion.div className={clsx("h-full rounded-full", r.disposition === "FAIL" ? "bg-crit" : r.disposition === "MANUAL_REVIEW" ? "bg-warn" : "bg-accent")} initial={false} animate={{ width: `${pct}%` }} transition={{ duration: 0.4 }} />
          </div>
          <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11.5px] text-ink-2">
            {Object.entries(r.counts).map(([k, v]) => <span key={k}><b className="font-semibold text-ink">{v}</b> {k.replace("_", " ").toLowerCase()}</span>)}
            <span className="ml-auto"><SourceBadge source={r.source_type} /></span>
          </div>
        </div>
      </div>
      {!running && (
        <p className="border-b border-line-soft bg-canvas/50 px-4 py-2 text-[12px] text-ink-2">
          {r.disposition === "FAIL" ? `FAIL: ${req.filter((x) => x.result === "FAIL").map((x) => x.check_name).join(", ")} failed (required).` :
            r.disposition === "MANUAL_REVIEW" ? `MANUAL REVIEW: required check(s) without conclusive evidence: ${req.filter((x) => !["PASS", "FAIL"].includes(x.result)).map((x) => x.check_name).join(", ")}.` :
              "PASS: every required check passed. Optional results are informational."}
          {r.corrections_before_run.length > 0 && <> Corrections recorded before this run: {r.corrections_before_run.map((c) => c.label).join("; ")}.</>}
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="table">
          <thead><tr><th scope="col">Check</th><th scope="col">Gate</th><th scope="col">Expected</th><th scope="col">Observed</th><th scope="col">Unit</th><th scope="col">Result</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>
            {r.results.map((x) => <ResultRow key={x.id} r={x} review={r.manual_reviews[x.check_key]} onReview={() => setRev(x)} />)}
            {running && r.profile_snapshot.checks.filter((c) => !r.results.some((x) => x.check_key === c.check_key)).map((c) => (
              <tr key={c.check_key} className="text-ink-3"><td className="pl-8">{c.check_key}</td><td>{c.required ? "Required" : "Optional"}</td><td colSpan={4}><span className="inline-flex items-center gap-1.5"><Loader2 className="h-3 w-3 animate-spin" aria-hidden />queued</span></td><td /></tr>
            ))}
          </tbody>
        </table>
      </div>
      {r.follow_up_actions.length > 0 && (
        <div className="border-t border-line-soft p-4">
          <div className="eyebrow mb-1">Follow-up actions</div>
          <ul className="space-y-1 text-[12.5px]">{[...new Set(r.follow_up_actions)].map((a) => <li key={a} className="flex gap-2"><ArrowRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" aria-hidden />{a}</li>)}</ul>
        </div>
      )}
      <Modal open={!!rev} onOpenChange={(o) => !o && setRev(null)} title={`Manual review: ${rev?.check_name}`} description="Recorded as a separate annotation. The stored check result never changes.">
        <div className="space-y-3">
          <p className="text-[12.5px] text-ink-2">{rev?.detail}</p>
          <fieldset className="flex gap-2"><legend className="label">Decision</legend>
            {(["accept", "reject"] as const).map((d) => <label key={d} className={clsx("flex cursor-pointer items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[13px] capitalize", decision === d ? "border-accent bg-accent-50" : "border-line")}><input type="radio" name="dec" checked={decision === d} onChange={() => setDecision(d)} />{d}</label>)}
          </fieldset>
          <div><label className="label" htmlFor="rv-note">Evidence reviewed (required)</label><textarea id="rv-note" className="input" rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Ran smartctl -H as root on the bench: PASSED for both drives." /></div>
          <div className="flex justify-end gap-2"><button className="btn-secondary" onClick={() => setRev(null)}>Cancel</button>
            <button className="btn-primary" disabled={note.trim().length < 3 || review.isPending} onClick={() => { if (!rev) { toast.push({ tone: "error", title: "No check selected" }); return; } review.mutate(); }}>Record review</button></div>
        </div>
      </Modal>
    </Panel>
  );
}

function Compare({ a, b }: { a: number; b: number }) {
  const q = useQuery({ queryKey: ["run", "compare", a, b], queryFn: () => api<any>(`/acceptance/compare?a=${a}&b=${b}`) });
  useEffect(() => { if (q.data?.b_disposition === "PASS") markDemo("compare"); }, [q.data]);
  if (q.isLoading) return <LoadingBlock rows={6} />;
  if (q.error) return <ErrorState error={q.error} />;
  const d = q.data;
  return (
    <Panel title="Run comparison" icon={<GitCompareArrows className="h-4 w-4" />} sub={`${d.a} → ${d.b}. Both runs are stored unchanged.`} bodyClass="">
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 border-b border-line-soft p-4">
        <div className="text-center"><div className="mono text-[12px] text-ink-2">{d.a}</div><div className="mt-1"><ResultBadge result={d.a_disposition} size="lg" /></div></div>
        <div className="flex flex-col items-center text-[11px] text-ink-2"><ArrowRight className="h-5 w-5 text-accent" aria-hidden />{d.corrections_between.length} correction(s)</div>
        <div className="text-center"><div className="mono text-[12px] text-ink-2">{d.b}</div><div className="mt-1"><ResultBadge result={d.b_disposition} size="lg" /></div></div>
      </div>
      {d.corrections_between.length > 0 && (
        <ul className="space-y-1.5 border-b border-line-soft bg-canvas/50 p-4">
          {d.corrections_between.map((c: any, i: number) => (
            <motion.li key={c.key} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.1 }} className="flex flex-wrap items-center gap-2 text-[12.5px]">
              <Wrench className="h-3.5 w-3.5 text-accent" aria-hidden /><span className="font-medium">{c.label}</span><SourceBadge source={c.source_type} compact /><span className="mono text-[11px] text-ink-3">{fmtTime(c.applied_at)} · {c.actor}</span>
            </motion.li>
          ))}
        </ul>
      )}
      <div className="overflow-x-auto">
        <table className="table">
          <thead><tr><th scope="col">Check</th><th scope="col">{d.a}</th><th scope="col">{d.b}</th><th scope="col">Changed</th></tr></thead>
          <tbody>
            {d.rows.map((row: any, i: number) => (
              <motion.tr key={row.check_key} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.03 }} className={clsx(row.changed && "bg-accent-50/50")}>
                <td className="font-medium">{row.check_name}{row.required ? "" : <span className="ml-1 text-[11px] text-ink-2">(optional)</span>}</td>
                <td><div className="flex items-center gap-2"><ResultBadge result={row.a?.result} /><span className="mono text-ink-2">{row.a?.observed ?? "—"} {row.a?.unit ?? ""}</span></div></td>
                <td><div className="flex items-center gap-2"><ResultBadge result={row.b?.result} /><span className={clsx("mono", row.changed ? "font-semibold text-ink" : "text-ink-2")}>{row.b?.observed ?? "—"} {row.b?.unit ?? ""}</span></div></td>
                <td>{row.changed ? <Pill className="border-accent/30 bg-accent-50 text-accent-700">changed</Pill> : <span className="text-[12px] text-ink-3">same</span>}</td>
              </motion.tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

export function AcceptanceDetail() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const q = useIntake(id);
  const collectors = useCollectorsAcc();
  const [collector, setCollector] = useState("simulator");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [handoff, setHandoff] = useState<Record<string, boolean>>({});
  const toast = useToast();
  useEffect(() => { if (q.data?.display_id === "INT-0001") markDemo("review"); }, [q.data?.display_id]);

  const start = useAction(() => post<any>(`/acceptance/intakes/${id}/runs`, { collector }, { idempotent: true }), {
    success: (r) => `${r.display_id} queued. The job runner is executing checks.`, onSuccess: (r) => setParams({ run: String(r.id) }),
  });
  const correct = useAction((key: string) => post(`/acceptance/intakes/${id}/corrections`, { key }), { success: "Simulated correction recorded" });
  const doHandoff = useAction(() => post(`/acceptance/intakes/${id}/handoff`, { checklist: handoff }), { success: "Handed off to provisioning" });

  const x = q.data;
  const completed = useMemo(() => (x?.runs ?? []).filter((r) => r.status === "completed"), [x]);
  if (q.isLoading) return <LoadingBlock rows={10} label="Loading intake" />;
  if (q.error || !x) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const runParam = params.get("run");
  const compare = params.get("compare")?.split(",").map(Number);
  const selRun = runParam ? Number(runParam) : x.runs.at(-1)?.id;
  const active = x.runs.some((r) => r.status !== "completed");
  const lastDone = completed.at(-1);
  const canHandoff = lastDone?.effective_disposition === "PASS" && x.status !== "handed_off";

  return (
    <div className="space-y-4">
      <div className="panel flex flex-col gap-3 p-4 md:flex-row md:items-center md:p-5">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><span className="mono text-[12.5px] text-ink-2">{x.display_id}</span><IntakeStatus s={x.status} /><SourceBadge source={x.source_type} /></div>
          <h1 className="mono mt-1 text-[22px] font-semibold">{x.hostname}</h1>
          <div className="mono text-[12px] text-ink-2">{x.asset_tag} · serial {x.serial_number}</div>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label htmlFor="coll" className="label">Collector</label>
            <select id="coll" className="input h-9 w-[250px]" value={collector} onChange={(e) => setCollector(e.target.value)}>
              {(collectors.data ?? []).map((c) => (
                <option key={c.key} value={c.key} disabled={!c.available || (c.key === "simulator" && !x.has_simulator_model) || (c.key === "linux_upload" && !x.has_upload)}>
                  {c.label}{c.note ? ` (${c.note})` : ""}{c.key === "linux_upload" && !x.has_upload ? " (upload first)" : ""}
                </option>
              ))}
            </select>
          </div>
          <button className="btn-secondary h-9" onClick={() => setUploadOpen(true)}><Upload className="h-4 w-4" aria-hidden />Upload collector output</button>
          <button className="btn-primary h-9" disabled={start.isPending || active} onClick={() => start.mutate()}>
            {active ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Play className="h-4 w-4" aria-hidden />}{x.runs.length ? "Start re-test" : "Start acceptance run"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
        <div className="space-y-4">
          <ExpectedCard x={x} />
          <Panel title="Runs" sub="Each run is a new immutable record" bodyClass="p-2">
            {x.runs.length === 0 ? <p className="p-2 text-[12.5px] text-ink-2">No runs yet.</p> : (
              <ol className="space-y-1">
                {[...x.runs].reverse().map((r) => (
                  <li key={r.id}>
                    <button onClick={() => setParams({ run: String(r.id) })} aria-current={selRun === r.id && !compare}
                      className={clsx("flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left transition-colors", selRun === r.id && !compare ? "bg-accent-50" : "hover:bg-canvas")}>
                      <span className="mono text-[12.5px] font-semibold">#{r.run_number}</span>
                      <ResultBadge result={r.status === "completed" ? r.disposition : null} />
                      <span className="mono ml-auto text-[11px] text-ink-3">{fmtTime(r.completed_at ?? r.created_at)}</span>
                    </button>
                  </li>
                ))}
              </ol>
            )}
            {completed.length >= 2 && (
              <button className="btn-secondary btn-sm mx-1 mb-1 mt-2 w-[calc(100%-0.5rem)]" onClick={() => setParams({ compare: `${completed[0].id},${completed.at(-1)!.id}` })}>
                <GitCompareArrows className="h-3.5 w-3.5" aria-hidden />Compare first and latest
              </button>
            )}
          </Panel>
          {x.has_simulator_model && (
            <Panel title="Simulated corrections" icon={<Wrench className="h-4 w-4" />} sub="Changes only the simulator's hardware model">
              {x.available_corrections.length === 0 && x.simulated_corrections.length === 0 ? <p className="text-[12.5px] text-ink-2">Corrections become available after a run fails on a correctable check.</p> : (
                <ul className="space-y-2">
                  {x.available_corrections.map((c) => (
                    <li key={c.key} className={clsx("rounded-xl border p-2.5", c.applied ? "border-ok/30 bg-ok-50/40" : "border-line")}>
                      <div className="text-[12.5px] font-medium">{c.label}</div>
                      <div className="mt-0.5 text-[11.5px] text-ink-2">Physical action: {c.physical_action}</div>
                      <div className="mt-2">{c.applied ? <span className="flex items-center gap-1 text-[12px] text-ok"><Check className="h-3.5 w-3.5" aria-hidden />Recorded</span> :
                        <button className="btn-secondary btn-sm" disabled={correct.isPending} onClick={() => correct.mutate(c.key)}>Record simulated correction</button>}</div>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          )}
          {(canHandoff || x.status === "handed_off") && (
            <Panel title="Provisioning handoff">
              {x.status === "handed_off" ? <p className="flex items-center gap-1.5 text-[13px] text-ok"><Check className="h-4 w-4" aria-hidden />Handed off to provisioning.</p> : (
                <form onSubmit={(e) => { e.preventDefault(); doHandoff.mutate(); }} className="space-y-2">
                  {Object.entries(x.handoff_checklist).map(([k, label]) => (
                    <label key={k} className="flex items-start gap-2 text-[12.5px]"><input type="checkbox" className="mt-0.5" checked={!!handoff[k]} onChange={(e) => setHandoff((h) => ({ ...h, [k]: e.target.checked }))} />{label}</label>
                  ))}
                  <button className="btn-primary btn-sm mt-1" disabled={Object.keys(x.handoff_checklist).some((k) => !handoff[k]) || doHandoff.isPending}>Hand off</button>
                </form>
              )}
            </Panel>
          )}
        </div>
        <div className="min-w-0 space-y-4">
          {compare && compare.length === 2 ? <><Compare a={compare[0]} b={compare[1]} /><button className="btn-ghost btn-sm" onClick={() => setParams({})}>← Back to run view</button></> :
            selRun ? <RunView key={selRun} runId={selRun} /> : (
              <div className="panel"><Empty title="No acceptance runs yet" icon={<Play className="h-5 w-5" />} action={<button className="btn-primary" onClick={() => start.mutate()}>Start acceptance run</button>}>
                The run snapshots the expected configuration, the profile and the observations, then executes each check in the backend job runner.
              </Empty></div>
            )}
        </div>
      </div>
      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} intakeId={x.id} onDone={() => { q.refetch(); setCollector("linux_upload"); toast.push({ tone: "ok", title: "Observations uploaded. Select “Uploaded Linux collector output” and start a run." }); }} />
    </div>
  );
}

function UploadDialog({ open, onOpenChange, intakeId, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; intakeId: number; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [src, setSrc] = useState<"LOCAL_LAB" | "IMPORTED_SAMPLE">("LOCAL_LAB");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!file) return;
    setBusy(true); setErr(null);
    const fd = new FormData(); fd.append("file", file); fd.append("source_type", src);
    try { await api(`/acceptance/intakes/${intakeId}/upload`, { method: "POST", body: fd }); onOpenChange(false); onDone(); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Upload Linux collector output" description="JSON produced by the read-only collector script, run by an operator on the target machine.">
      <div className="space-y-3">
        <div className="rounded-lg bg-nav p-3"><code className="mono block whitespace-pre-wrap text-[11.5px] text-[#D7DEEA]">python3 collectors/rackops_collect.py --data-iface eth1 &gt; observations.json</code></div>
        <p className="text-[12px] text-ink-2">The script only reads /proc, /sys, lsblk and ip. Disk health and the kernel log need root, so without it they are reported as unsupported and the run goes to MANUAL REVIEW. Upload limit 512 KiB. Secrets are redacted on import.</p>
        <div><label className="label" htmlFor="up-file">File</label><input id="up-file" type="file" accept="application/json,.json" className="block w-full text-[12.5px]" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></div>
        <fieldset><legend className="label">Source label</legend>
          <div className="flex gap-2">{(["LOCAL_LAB", "IMPORTED_SAMPLE"] as const).map((s) => (
            <label key={s} className={clsx("flex cursor-pointer items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px]", src === s ? "border-accent bg-accent-50" : "border-line")}><input type="radio" name="src" checked={src === s} onChange={() => setSrc(s)} />{s === "LOCAL_LAB" ? "Collected from my lab hardware" : "Imported sample"}</label>
          ))}</div>
        </fieldset>
        {err && <p className="rounded-lg bg-crit-50 px-3 py-2 text-[12.5px] text-crit" role="alert">{err}</p>}
        <div className="flex justify-end gap-2"><button className="btn-secondary" onClick={() => onOpenChange(false)}>Cancel</button><button className="btn-primary" disabled={!file || busy} onClick={submit}>Upload</button></div>
      </div>
    </Modal>
  );
}
