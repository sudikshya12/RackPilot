import * as Dialog from "@radix-ui/react-dialog";
import clsx from "clsx";
import { motion } from "framer-motion";
import { AlertTriangle, Check, Copy, Inbox, RefreshCw, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "@/api/client";

export function Panel({ title, actions, children, className, bodyClass, icon, sub, id }: {
  title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string; icon?: ReactNode; sub?: ReactNode; id?: string;
}) {
  return (
    <section className={clsx("panel min-w-0", className)} aria-labelledby={id}>
      {(title || actions) && (
        <header className="panel-head">
          <div className="flex min-w-0 items-center gap-2">
            {icon && <span className="text-ink-2" aria-hidden>{icon}</span>}
            <div className="min-w-0">
              {title && <h2 id={id} className="panel-title truncate">{title}</h2>}
              {sub && <div className="truncate text-[12px] text-ink-2">{sub}</div>}
            </div>
          </div>
          {actions && <div className="flex max-w-full flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={clsx(bodyClass ?? "p-4")}>{children}</div>
    </section>
  );
}

export function PageHeader({ title, eyebrow, actions, children }: { title: ReactNode; eyebrow?: ReactNode; actions?: ReactNode; children?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0">
        {eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}
        <h1 className="text-[22px] font-semibold leading-tight text-ink md:text-[24px]">{title}</h1>
        {children && <div className="mt-1.5 max-w-3xl text-[13.5px] leading-relaxed text-ink-2">{children}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, sub, to, tone = "default", icon, delay = 0 }: {
  label: string; value: ReactNode; sub?: ReactNode; to?: string; tone?: "default" | "ok" | "warn" | "crit" | "accent"; icon?: ReactNode; delay?: number;
}) {
  const subCls = { default: "text-ink-2", ok: "text-ink-2", warn: "text-warn", crit: "text-crit", accent: "text-accent-700" }[tone];
  const bar = { default: "", ok: "", warn: "bg-warn", crit: "bg-crit", accent: "bg-accent" }[tone];
  const inner = (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22, delay, ease: [0.2, 0.8, 0.2, 1] }}
      className="panel group relative h-full overflow-hidden px-4 py-3.5 transition-[box-shadow,border-color] duration-200 hover:border-line-strong hover:shadow-lift">
      {bar && <span className={clsx("absolute inset-y-0 left-0 w-[3px]", bar)} aria-hidden />}
      <div className="flex items-start justify-between gap-2">
        <div className="text-[12px] font-medium text-ink-2">{label}</div>
        {icon && <span className="text-ink-3 transition-colors group-hover:text-accent" aria-hidden>{icon}</span>}
      </div>
      <div className="mt-1.5 text-[26px] font-semibold leading-none tabular-nums text-ink">{value}</div>
      {sub && <div className={clsx("mt-1.5 text-[12px]", subCls)}>{sub}</div>}
    </motion.div>
  );
  return to ? <Link to={to} className="block h-full rounded-xl focus-visible:outline-offset-4" aria-label={`${label}: open filtered view`}>{inner}</Link> : inner;
}

export function Empty({ title, children, icon, action }: { title: string; children?: ReactNode; icon?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-10 text-center">
      <div className="mb-3 grid h-10 w-10 place-items-center rounded-full bg-canvas text-ink-3">{icon ?? <Inbox className="h-5 w-5" aria-hidden />}</div>
      <div className="text-[13.5px] font-medium text-ink">{title}</div>
      {children && <div className="mt-1 max-w-sm text-[12.5px] text-ink-2">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("skeleton", className)} aria-hidden />;
}

export function LoadingBlock({ rows = 4, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div className="space-y-2.5 p-4" role="status" aria-label={label}>
      {Array.from({ length: rows }).map((_, i) => <Skeleton key={i} className={clsx("h-5", i % 3 === 2 ? "w-2/3" : "w-full")} />)}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const msg = error instanceof ApiError ? error.message : "Something went wrong while loading this view.";
  return (
    <div className="flex items-start gap-3 rounded-xl border border-crit-100 bg-crit-50/50 p-4" role="alert">
      <AlertTriangle className="mt-0.5 h-4 w-4 text-crit" aria-hidden />
      <div className="flex-1 text-[13px]">
        <div className="font-medium text-ink">Could not load data</div>
        <div className="text-ink-2">{msg}</div>
      </div>
      {retry && <button className="btn-secondary btn-sm" onClick={retry}><RefreshCw className="h-3.5 w-3.5" aria-hidden />Retry</button>}
    </div>
  );
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button type="button" className="btn-ghost btn-sm" aria-label={`${label}: ${text}`}
      onClick={async () => { try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1200); } catch { /* clipboard unavailable */ } }}>
      {done ? <Check className="h-3.5 w-3.5 text-ok" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
      <span className="sr-only md:not-sr-only">{done ? "Copied" : label}</span>
    </button>
  );
}

export function Modal({ open, onOpenChange, title, description, children, wide }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: string; description?: string; children: ReactNode; wide?: boolean;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[60] bg-nav/40 backdrop-blur-[2px] data-[state=open]:animate-[fadeIn_150ms_ease-out]" />
        <Dialog.Content className={clsx("fixed left-1/2 top-1/2 z-[61] max-h-[88vh] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-2xl border border-line bg-white shadow-lift focus:outline-none", wide ? "max-w-3xl" : "max-w-lg")}>
          <div className="flex items-start justify-between gap-4 border-b border-line-soft px-5 py-4">
            <div>
              <Dialog.Title className="text-[15px] font-semibold text-ink">{title}</Dialog.Title>
              {description && <Dialog.Description className="mt-0.5 text-[12.5px] text-ink-2">{description}</Dialog.Description>}
            </div>
            <Dialog.Close className="rounded-md p-1 text-ink-3 hover:bg-canvas hover:text-ink" aria-label="Close dialog"><X className="h-4 w-4" /></Dialog.Close>
          </div>
          <div className="p-5">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function KV({ k, v, mono }: { k: ReactNode; v: ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5 text-[13px]">
      <dt className="shrink-0 text-ink-2">{k}</dt>
      <dd className={clsx("min-w-0 truncate text-right text-ink", mono && "mono")}>{v}</dd>
    </div>
  );
}

export function Field({ label, children, hint, htmlFor }: { label: string; children: ReactNode; hint?: string; htmlFor: string }) {
  return (
    <div>
      <label className="label" htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && <p className="mt-1 text-[11.5px] text-ink-2">{hint}</p>}
    </div>
  );
}
