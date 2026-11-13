import { Fragment, type ReactNode } from "react";

/** Minimal, safe Markdown renderer for generated summaries (headings, lists, bold, italics, inline code). No raw HTML. */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|_[^_]+_)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    if (t.startsWith("**")) out.push(<strong key={k++} className="font-semibold text-ink">{t.slice(2, -2)}</strong>);
    else if (t.startsWith("`")) out.push(<code key={k++} className="mono rounded bg-canvas px-1 text-[11.5px]">{t.slice(1, -1)}</code>);
    else out.push(<em key={k++} className="text-ink-2">{t.slice(1, -1)}</em>);
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) {
      blocks.push(<ul key={`l${blocks.length}`} className="my-2 space-y-1 pl-4">{list.map((l, i) => <li key={i} className="list-disc text-[13px] leading-relaxed text-ink marker:text-ink-3">{inline(l)}</li>)}</ul>);
      list = [];
    }
  };
  lines.forEach((ln, i) => {
    if (ln.startsWith("- ")) { list.push(ln.slice(2)); return; }
    flush();
    if (ln.startsWith("# ")) blocks.push(<h2 key={i} className="mb-2 text-[18px] font-semibold text-ink">{inline(ln.slice(2))}</h2>);
    else if (ln.startsWith("## ")) blocks.push(<h3 key={i} className="mb-1 mt-4 text-2xs font-semibold uppercase tracking-[0.08em] text-ink-2">{inline(ln.slice(3))}</h3>);
    else if (ln.trim()) blocks.push(<p key={i} className="my-1 text-[13px] leading-relaxed text-ink">{inline(ln)}</p>);
  });
  flush();
  return <Fragment>{blocks}</Fragment>;
}
