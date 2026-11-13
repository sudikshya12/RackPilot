import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import { Activity, BookOpen, Boxes, ChevronRight, ClipboardCheck, Gauge, Info, Menu, Network, PlayCircle, Search, Settings, Siren, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useNavigationType } from "react-router-dom";
import { api } from "@/api/client";
import { useDemos, useOverview, useSettings } from "@/api/hooks";
import { useEventStream, type StreamState } from "@/lib/sse";
import { DemoDock } from "./DemoDock";

type NavItem = { to: string; label: string; icon: typeof Gauge; badge?: "incidents"; match?: string[] };
const PRIMARY: NavItem[] = [
  { to: "/", label: "Overview", icon: Gauge, match: ["/", "/operations"] },
  { to: "/incidents", label: "Incidents", icon: Siren, badge: "incidents" },
  { to: "/acceptance", label: "Acceptance", icon: ClipboardCheck },
  { to: "/infrastructure", label: "Infrastructure", icon: Network },
  { to: "/assets", label: "Inventory", icon: Boxes, match: ["/assets", "/spares", "/returns"] },
  { to: "/runbooks", label: "Runbooks", icon: BookOpen },
];
const UTILITY: NavItem[] = [
  { to: "/demo", label: "Demonstrations", icon: PlayCircle },
  { to: "/settings", label: "Settings", icon: Settings },
  { to: "/about", label: "About & Documentation", icon: Info, match: ["/about", "/projects"] },
];

const CRUMB_LABELS: Record<string, string> = {
  operations: "Overview", incidents: "Incidents", acceptance: "Acceptance", infrastructure: "Infrastructure", assets: "Inventory",
  spares: "Spare parts", returns: "Returns", runbooks: "Runbooks", projects: "Case studies", demo: "Demonstrations", settings: "Settings",
  runs: "Runs", report: "Report", about: "About & Documentation",
};

function isActive(item: NavItem, path: string) {
  const prefixes = item.match ?? [item.to];
  return prefixes.some((p) => (p === "/" ? path === "/" : path === p || path.startsWith(p + "/")));
}

function NavRow({ item, open, onNavigate }: { item: NavItem; open: number; onNavigate?: () => void }) {
  const loc = useLocation();
  const active = isActive(item, loc.pathname);
  return (
    <li>
      <Link to={item.to} onClick={onNavigate} aria-current={active ? "page" : undefined}
        className={clsx("group relative flex items-center gap-2.5 rounded-lg px-2.5 py-[7px] text-[13px] transition-colors duration-150",
          active ? "bg-white/[0.07] text-white" : "text-nav-text/90 hover:bg-white/[0.04] hover:text-white")}>
        {active && <motion.span layoutId="nav-active" className="absolute inset-y-2 left-0 w-[2px] rounded-r bg-accent-300" transition={{ duration: 0.2 }} />}
        <item.icon className={clsx("h-4 w-4 shrink-0", active ? "text-accent-300" : "text-nav-muted group-hover:text-nav-text")} aria-hidden />
        <span className="flex-1 truncate">{item.label}</span>
        {item.badge === "incidents" && open > 0 && (
          <span className="rounded-full bg-crit/90 px-1.5 text-[10.5px] font-semibold leading-[17px] text-white" aria-label={`${open} open incidents`}>{open}</span>
        )}
      </Link>
    </li>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const ov = useOverview();
  const open = ov.data?.open_incidents?.total ?? 0;
  return (
    <nav aria-label="Primary" className="dark-surface flex h-full flex-col bg-nav text-nav-text">
      <Link to="/" onClick={onNavigate} className="flex items-center gap-2.5 px-4 pb-5 pt-5">
        <RackMark />
        <div className="leading-tight">
          <div className="text-[14px] font-semibold tracking-[-0.01em] text-white">RackOps Lab</div>
          <div className="text-[11px] text-nav-muted">Data Center Operations</div>
        </div>
      </Link>
      <ul className="flex-1 space-y-0.5 overflow-y-auto px-2.5">
        {PRIMARY.map((it) => <NavRow key={it.to} item={it} open={open} onNavigate={onNavigate} />)}
      </ul>
      <ul className="space-y-0.5 border-t border-white/[0.06] px-2.5 py-3">
        {UTILITY.map((it) => <NavRow key={it.to} item={it} open={0} onNavigate={onNavigate} />)}
      </ul>
    </nav>
  );
}

function RackMark() {
  return (
    <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden>
      <rect x="5" y="2" width="22" height="28" rx="4" fill="#18233A" stroke="#2A3755" />
      {[7, 12.5, 18].map((y, i) => (
        <g key={y}>
          <rect x="8.5" y={y} width="15" height="3.6" rx="1" fill={i === 0 ? "#087F8C" : "#2A3755"} />
          <circle cx="21" cy={y + 1.8} r="0.9" fill={i === 1 ? "#5DB3BC" : "#18794E"} />
        </g>
      ))}
      <rect x="8.5" y="24" width="15" height="2.2" rx="1" fill="#223050" />
    </svg>
  );
}

function StreamIndicator({ state }: { state: StreamState }) {
  const map = {
    live: { cls: "bg-ok", text: "Events connected", tip: "Connected to the backend event stream. This is the app connection, not a hardware monitor." },
    connecting: { cls: "bg-ink-3", text: "Connecting", tip: "Opening the event stream" },
    reconnecting: { cls: "bg-warn", text: "Reconnecting", tip: "Event stream interrupted. Missed events replay on reconnect." },
    offline: { cls: "bg-crit", text: "Offline", tip: "Cannot reach the backend. Displayed data may be stale." },
  }[state];
  return (
    <div className="hidden items-center gap-1.5 text-[12px] text-ink-2 sm:flex" title={map.tip} role="status" aria-live="polite">
      <span className={clsx("led", map.cls)} aria-hidden />
      <span className={clsx("hidden xl:inline", state === "offline" && "font-medium text-crit")}>{map.text}</span>
      <span className="sr-only xl:hidden">{map.text}</span>
    </div>
  );
}

export function SourceIndicator() {
  const [open, setOpen] = useState(false);
  const settings = useSettings();
  const ov = useOverview();
  const live = settings.data?.livelab?.enabled;
  const redfish = settings.data?.integrations?.redfish?.status === "configured";
  const localSources = [live && "Live-lab target", redfish && "Redfish endpoint"].filter(Boolean) as string[];
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);
  const drills = ov.data?.simulation_active ?? 0;
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="dialog"
        className="flex h-8 items-center gap-1.5 rounded-lg border border-line bg-white px-2.5 text-[12px] font-medium text-ink-2 transition-colors hover:border-line-strong hover:text-ink">
        <span className="led bg-sim" aria-hidden />
        <span className="hidden sm:inline">{localSources.length ? "Simulation + local lab" : "Simulation mode"}</span>
        <span className="sm:hidden">Sim</span>
        {drills > 0 && <span className="hidden rounded bg-sim-50 px-1 text-[11px] text-sim md:inline">{drills} running</span>}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div role="dialog" aria-label="Data sources" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.15 }}
            className="absolute right-0 top-10 z-50 w-[min(300px,calc(100vw-2rem))] rounded-xl border border-line bg-white p-4 text-[12.5px] shadow-lift">
            <div className="font-semibold text-ink">Data sources</div>
            <dl className="mt-2 space-y-2 text-ink-2">
              <div><dt className="font-medium text-ink">Simulated</dt><dd>Incidents, probes, evidence and acceptance hardware come from a deterministic simulator. Each item is labeled SIMULATED.</dd></div>
              <div><dt className="font-medium text-ink">Modeled rack</dt><dd>Racks, cabling and power are a synthetic documentation model, not discovered hardware.</dd></div>
              <div><dt className="font-medium text-ink">Local lab</dt><dd>{localSources.length ? `Connected: ${localSources.join(", ")}.` : "None connected."}</dd></div>
              {settings.data?.mode === "hosted_demo" && (
                <div><dt className="font-medium text-ink">Hosted demo</dt><dd>This online demo uses temporary data that may reset at any time. Run it locally for persistent data and the live-lab target.</dd></div>
              )}
            </dl>
            <Link to="/settings" onClick={() => setOpen(false)} className="mt-3 inline-block font-medium text-accent-700 hover:underline">Configure sources</Link>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Breadcrumbs() {
  const loc = useLocation();
  const parts = loc.pathname.split("/").filter(Boolean);
  if (parts.length === 0) return <div className="truncate text-[13px] font-medium text-ink">Overview</div>;
  return (
    <ol className="flex min-w-0 items-center gap-1 text-[13px]" aria-label="Breadcrumb">
      <li><Link to="/" className="text-ink-2 hover:text-ink">Overview</Link></li>
      {parts.map((p, i) => {
        const to = "/" + parts.slice(0, i + 1).join("/");
        const last = i === parts.length - 1;
        const label = CRUMB_LABELS[p] ?? decodeURIComponent(p);
        return (
          <li key={to} className="flex min-w-0 items-center gap-1">
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-ink-3" aria-hidden />
            {last ? <span className="truncate font-medium text-ink" aria-current="page">{label}</span> :
              <Link to={to} className="truncate text-ink-2 hover:text-ink">{label}</Link>}
          </li>
        );
      })}
    </ol>
  );
}

function GlobalSearch() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [results, setResults] = useState<{ type: string; label: string; sub: string; route: string }[]>([]);
  const [active, setActive] = useState(0);
  const nav = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen(true); }
      if (e.key === "/" && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) { e.preventDefault(); setOpen(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => { if (open) setTimeout(() => inputRef.current?.focus(), 30); else { setQ(""); setResults([]); } }, [open]);
  useEffect(() => {
    if (!q.trim()) { setResults([]); return; }
    const t = setTimeout(() => api<any[]>(`/search?q=${encodeURIComponent(q)}`).then((r) => { setResults(r); setActive(0); }).catch(() => setResults([])), 140);
    return () => clearTimeout(t);
  }, [q]);

  const go = (r: { route: string }) => { setOpen(false); nav(r.route); };

  return (
    <>
      <button onClick={() => setOpen(true)} className="flex h-8 w-full min-w-0 max-w-[280px] items-center gap-2 rounded-lg border border-line bg-white px-2.5 text-[12.5px] text-ink-3 transition-colors hover:border-line-strong"
        aria-label="Search assets, incidents, serials and cables">
        <Search className="h-3.5 w-3.5" aria-hidden />
        <span className="flex-1 truncate text-left">Search assets, incidents, serials…</span>
        <span className="kbd hidden sm:inline-flex">⌘K</span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div className="fixed inset-0 z-[70] flex items-start justify-center bg-nav/30 px-4 pt-[12vh] backdrop-blur-[2px]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }} onMouseDown={(e) => e.target === e.currentTarget && setOpen(false)}>
            <motion.div role="dialog" aria-modal="true" aria-label="Global search" className="w-full max-w-xl overflow-hidden rounded-2xl border border-line bg-white shadow-lift"
              initial={{ y: -8, scale: 0.985 }} animate={{ y: 0, scale: 1 }} exit={{ y: -8, scale: 0.985 }} transition={{ duration: 0.18 }}>
              <div className="flex items-center gap-2 border-b border-line-soft px-4">
                <Search className="h-4 w-4 text-ink-3" aria-hidden />
                <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search query" placeholder="lab-srv-04, INC-0001, SIM-PSU, CBL-0107…"
                  className="h-12 flex-1 bg-transparent text-[14px] outline-none placeholder:text-ink-3"
                  onKeyDown={(e) => {
                    if (e.key === "Escape") setOpen(false);
                    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)); }
                    if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
                    if (e.key === "Enter" && results[active]) go(results[active]);
                  }} />
                <span className="kbd">Esc</span>
              </div>
              <ul className="max-h-[50vh] overflow-auto p-1.5" role="listbox" aria-label="Search results">
                {q && results.length === 0 && <li className="px-3 py-6 text-center text-[13px] text-ink-2">No matching records.</li>}
                {!q && <li className="px-3 py-5 text-center text-[12.5px] text-ink-2">Search devices, assets, serial numbers, incidents, intakes and cable labels.</li>}
                {results.map((r, i) => (
                  <li key={`${r.type}-${r.label}-${i}`} role="option" aria-selected={i === active}>
                    <button onMouseEnter={() => setActive(i)} onClick={() => go(r)}
                      className={clsx("flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left", i === active ? "bg-accent-50" : "hover:bg-canvas")}>
                      <span className="w-16 shrink-0 text-2xs font-semibold uppercase tracking-wider text-ink-3">{r.type}</span>
                      <span className="mono shrink-0 font-medium text-ink">{r.label}</span>
                      <span className="truncate text-[12px] text-ink-2">{r.sub}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const stream = useEventStream();
  const [mobileOpen, setMobileOpen] = useState(false);
  const loc = useLocation();
  const demos = useDemos();
  const [dismissed, setDismissed] = useState<string[]>(() => { try { return JSON.parse(sessionStorage.getItem("rackops-demo-dismissed") ?? "[]"); } catch { return []; } });
  const dismiss = (runId: string) => {
    const next = [...dismissed, runId];
    setDismissed(next);
    try { sessionStorage.setItem("rackops-demo-dismissed", JSON.stringify(next)); } catch { /* storage unavailable */ }
  };
  const activeDemo = useMemo(() => demos.data?.find((d) => d.run && ["running", "awaiting_operator", "paused"].includes(d.run.status) && !d.complete)
    ?? demos.data?.find((d) => d.run && d.complete && !dismissed.includes(d.run.display_id) && Date.now() - new Date(d.run.started_at).getTime() < 3600_000),
  [demos.data, dismissed]);
  const mainRef = useRef<HTMLElement>(null);
  const prevPath = useRef(loc.pathname);
  const navType = useNavigationType();
  useEffect(() => {
    setMobileOpen(false);
    // Move focus to the new page on user navigation only: not on first load or redirects, so Tab still reaches the skip link.
    if (prevPath.current === loc.pathname) return;
    prevPath.current = loc.pathname;
    if (navType === "REPLACE") return;
    window.scrollTo({ top: 0 });
    mainRef.current?.focus({ preventScroll: true });
  }, [loc.pathname]);

  return (
    <div className="app-root min-h-screen lg:pl-[232px]">
      <a href="#main" className="sr-only z-[100] rounded bg-white px-3 py-2 focus:not-sr-only focus:fixed focus:left-2 focus:top-2">Skip to content</a>
      <aside className="no-print fixed inset-y-0 left-0 z-40 hidden w-[232px] lg:block"><Sidebar /></aside>
      <AnimatePresence>
        {mobileOpen && (
          <>
            <motion.div className="fixed inset-0 z-40 bg-nav/40 lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setMobileOpen(false)} />
            <motion.aside className="fixed inset-y-0 left-0 z-50 w-[260px] lg:hidden" initial={{ x: -280 }} animate={{ x: 0 }} exit={{ x: -280 }} transition={{ duration: 0.22, ease: [0.2, 0.8, 0.2, 1] }}
              role="dialog" aria-modal="true" aria-label="Navigation">
              <button onClick={() => setMobileOpen(false)} className="absolute right-2 top-4 z-10 rounded-md p-1.5 text-nav-muted hover:text-white" aria-label="Close navigation"><X className="h-4 w-4" /></button>
              <Sidebar onNavigate={() => setMobileOpen(false)} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
      <header className="no-print sticky top-0 z-30 border-b border-line bg-canvas/85 backdrop-blur-md">
        <div className="flex h-14 items-center gap-2 px-4 sm:gap-3 md:px-6">
          <button className="rounded-md p-1.5 text-ink-2 hover:bg-white lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu className="h-5 w-5" /></button>
          <div className="hidden min-w-0 flex-1 md:block"><Breadcrumbs /></div>
          <div className="flex min-w-0 flex-1 justify-end md:flex-none"><GlobalSearch /></div>
          <SourceIndicator />
          <StreamIndicator state={stream.state} />
        </div>
        {stream.state === "offline" && (
          <div className="flex items-center gap-2 border-t border-crit-100 bg-crit-50 px-6 py-1.5 text-[12px] text-crit" role="alert">
            <Activity className="h-3.5 w-3.5" aria-hidden />Backend unreachable. Showing the last loaded data, which may be stale. Reconnecting automatically.
          </div>
        )}
      </header>
      <main id="main" ref={mainRef} tabIndex={-1} className={clsx("mx-auto max-w-[1480px] px-4 py-5 outline-none md:px-6 md:py-6", activeDemo && (activeDemo.complete ? "pb-36" : "pb-24"))}>
        <AnimatePresence mode="wait">
          <motion.div key={loc.pathname} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.18, ease: [0.2, 0.8, 0.2, 1] }}>
            {children}
          </motion.div>
        </AnimatePresence>
      </main>
      <AnimatePresence>{activeDemo && <DemoDock key={activeDemo.key + String(activeDemo.complete)} demo={activeDemo} onDismiss={() => activeDemo.run && dismiss(activeDemo.run.display_id)} />}</AnimatePresence>
    </div>
  );
}
