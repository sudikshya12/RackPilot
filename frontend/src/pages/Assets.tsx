import clsx from "clsx";
import { motion } from "framer-motion";
import { Boxes, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useAssets } from "@/api/hooks";
import { LifecycleBadge, Pill } from "@/components/ui/Badges";
import { Empty, ErrorState, LoadingBlock, PageHeader, Panel } from "@/components/ui/Primitives";
import { human } from "@/lib/format";

const STATUSES = ["received", "stored", "installed", "active", "quarantined", "in_repair", "pending_return", "returned", "decommissioned"];
const TYPES = ["server", "switch", "psu", "patch_panel", "dimm", "transceiver", "disk"];

const LEGEND: [string, string][] = [
  ["received", "Delivered, not yet checked in"],
  ["stored", "In a known storage location"],
  ["installed", "Physically installed in a device"],
  ["active", "In service"],
  ["quarantined", "Removed or suspect; held for review"],
  ["in_repair", "Undergoing repair"],
  ["pending_return", "Return record open"],
  ["returned", "Returned to vendor"],
  ["decommissioned", "Permanently retired"],
];

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} aria-pressed={active}
      className={clsx("h-7 rounded-full border px-2.5 text-[12px] font-medium capitalize transition-colors duration-150",
        active ? "border-accent bg-accent text-white" : "border-line bg-white text-ink-2 hover:border-line-strong hover:text-ink")}>{children}</button>
  );
}

function warranty(w: string) {
  return w === "known_active" ? "Active" : w === "known_expired" ? "Expired" : "Unknown";
}

export function Assets() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const get = (k: string) => (params.get(k) ?? "").split(",").filter(Boolean);
  const toggle = (k: string, v: string) => setParams((p) => {
    const cur = new Set(get(k));
    cur.has(v) ? cur.delete(v) : cur.add(v);
    cur.size ? p.set(k, [...cur].join(",")) : p.delete(k);
    return p;
  });

  useEffect(() => {
    const t = setTimeout(() => setParams((p) => { q.trim() ? p.set("q", q.trim()) : p.delete("q"); return p; }, { replace: true }), 250);
    return () => clearTimeout(t);
  }, [q, setParams]);

  const qs = useMemo(() => {
    const p = new URLSearchParams();
    if (params.get("status")) p.set("status", params.get("status")!);
    if (params.get("type")) p.set("asset_type", params.get("type")!);
    if (params.get("q")) p.set("q", params.get("q")!);
    return p.toString();
  }, [params]);
  const assets = useAssets(qs);
  const filtered = ["status", "type", "q"].some((k) => params.get(k));

  return (
    <div className="space-y-5">
      <PageHeader title="Assets">Serialized equipment and its lifecycle state.</PageHeader>

      <div className="panel space-y-2.5 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="asset-q" className="sr-only">Search assets</label>
          <div className="relative w-full max-w-xs">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-3" aria-hidden />
            <input id="asset-q" className="input h-8 pl-8" placeholder="Asset tag, serial or model…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          {filtered && <button className="btn-ghost btn-sm ml-auto" onClick={() => { setQ(""); setParams({}); }}>Clear filters</button>}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="eyebrow mr-1 w-14">Status</span>
          {STATUSES.map((s) => <Chip key={s} active={get("status").includes(s)} onClick={() => toggle("status", s)}>{human(s)}</Chip>)}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="eyebrow mr-1 w-14">Type</span>
          {TYPES.map((s) => <Chip key={s} active={get("type").includes(s)} onClick={() => toggle("type", s)}>{human(s)}</Chip>)}
        </div>
      </div>

      <Panel title={`Assets${assets.data ? ` · ${assets.data.length}` : ""}`} icon={<Boxes className="h-4 w-4" />} bodyClass="">
        {assets.isLoading ? <LoadingBlock rows={8} /> : assets.error ? <div className="p-4"><ErrorState error={assets.error} retry={() => assets.refetch()} /></div> : !assets.data?.length ? (
          <Empty title={filtered ? "No assets match these filters" : "No assets recorded"}>Try clearing filters or searching by serial number.</Empty>
        ) : (
          <>
            <div className="hidden overflow-x-auto md:block">
              <table className="table">
                <caption className="sr-only">Asset inventory</caption>
                <thead><tr>
                  <th scope="col">Asset tag</th><th scope="col">Serial</th><th scope="col">Type</th><th scope="col">Model</th><th scope="col">Lifecycle</th>
                  <th scope="col">Location</th><th scope="col">Installed in</th><th scope="col">Warranty</th>
                </tr></thead>
                <tbody>
                  {assets.data.map((a, i) => (
                    <motion.tr key={a.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: Math.min(i * 0.015, 0.25), duration: 0.18 }}>
                      <td><Link to={`/assets/${a.id}`} className="mono font-semibold text-ink hover:text-accent-700">{a.display_id}</Link>
                        {a.origin === "simulation" && <div><Pill className="mt-0.5 border-sim/25 bg-sim-50 text-sim">simulation</Pill></div>}</td>
                      <td className="mono text-ink-2">{a.serial_number}</td>
                      <td className="capitalize">{human(a.asset_type)}</td>
                      <td className="mono">{a.model}</td>
                      <td><LifecycleBadge status={a.status} /></td>
                      <td className="max-w-[200px] truncate text-ink-2" title={a.location}>{a.location || "—"}</td>
                      <td>{a.installed_in ? <Link to={`/infrastructure?device=${a.installed_in.display_id}`} className="mono text-accent-700 hover:underline">{a.installed_in.display_id}</Link> : <span className="text-ink-3">—</span>}</td>
                      <td className={clsx(a.warranty_status === "unknown" && "text-warn")}>{warranty(a.warranty_status)}</td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="divide-y divide-line-soft md:hidden">
              {assets.data.map((a) => (
                <li key={a.id}>
                  <Link to={`/assets/${a.id}`} className="block px-4 py-3">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="mono font-semibold">{a.display_id}</span><LifecycleBadge status={a.status} />
                      {a.origin === "simulation" && <Pill className="border-sim/25 bg-sim-50 text-sim">simulation</Pill>}
                    </div>
                    <div className="mono mt-0.5 text-[11.5px] text-ink-2">{a.serial_number} · {a.model}</div>
                    <div className="mt-0.5 text-[12px] text-ink-2">{a.installed_in ? `In ${a.installed_in.display_id}` : a.location || "No location"} · Warranty {warranty(a.warranty_status)}</div>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </Panel>

      <Panel title="Lifecycle states" sub="Main path: Received → Stored → Installed → Active. Transitions are validated server-side.">
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {LEGEND.map(([s, d]) => (
            <li key={s} className="flex items-center gap-2 text-[12.5px]"><LifecycleBadge status={s} /><span className="text-ink-2">{d}</span></li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
