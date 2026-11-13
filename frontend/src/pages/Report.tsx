import { ExternalLink, FileJson, Printer } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link, useParams } from "react-router-dom";
import { post } from "@/api/client";
import { useRun } from "@/api/hooks";
import { ResultBadge, SourceBadge } from "@/components/ui/Badges";
import { ErrorState, LoadingBlock, PageHeader } from "@/components/ui/Primitives";

export function Report() {
  const { runId } = useParams();
  const q = useRun(runId);
  const frame = useRef<HTMLIFrameElement>(null);
  useEffect(() => { if (q.data?.disposition === "PASS") post("/demos/acceptance-retest/view/report").catch(() => undefined); }, [q.data?.disposition]);
  if (q.isLoading) return <LoadingBlock rows={6} />;
  if (q.error || !q.data) return <ErrorState error={q.error} />;
  const r = q.data;
  return (
    <div className="space-y-4">
      <PageHeader eyebrow="Acceptance report" title={<span className="mono">{r.hostname} · run #{r.run_number}</span>}
        actions={<>
          <button className="btn-primary" onClick={() => frame.current?.contentWindow?.print()}><Printer className="h-4 w-4" aria-hidden />Print / PDF</button>
          <a className="btn-secondary" href={`/api/acceptance/runs/${r.id}/report.html`} target="_blank" rel="noreferrer"><ExternalLink className="h-4 w-4" aria-hidden />Open HTML</a>
          <a className="btn-secondary" href={`/api/acceptance/runs/${r.id}/report.json`} download><FileJson className="h-4 w-4" aria-hidden />JSON export</a>
          <Link className="btn-ghost" to={`/acceptance/${r.intake_id}?run=${r.id}`}>Back to run</Link>
        </>}>
        <span className="inline-flex flex-wrap items-center gap-2"><ResultBadge result={r.disposition} /><SourceBadge source={r.source_type} />
          Rendered by the backend from the persisted run record <span className="mono">{r.display_id}</span>. Later changes to the intake do not alter it.</span>
      </PageHeader>
      <div className="panel overflow-hidden">
        <iframe ref={frame} title={`Acceptance report ${r.display_id}`} src={`/api/acceptance/runs/${r.id}/report.html`} className="h-[calc(100vh-260px)] min-h-[560px] w-full bg-canvas" />
      </div>
    </div>
  );
}
