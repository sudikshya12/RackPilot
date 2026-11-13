import clsx from "clsx";
import { motion } from "framer-motion";
import { AlertTriangle, ClipboardCheck, Zap } from "lucide-react";
import { useMemo, useState } from "react";
import type { DeviceCard, Rack } from "@/api/types";

const U_PX = 19;

type Face = "front" | "rear";

function healthLed(h: string) {
  return h === "critical" ? "bg-[#FF5A67] ring-2 ring-[#FF5A67]/30" : h === "degraded" ? "bg-[#F2A93B] ring-2 ring-[#F2A93B]/25" : h === "healthy" ? "bg-[#3BD38B]" : "bg-[#6B7789]";
}

/** Units that contain equipment or planned positions, padded by one unit and clamped to the rack. */
export function populatedRange(rack: Rack): [number, number] {
  const us: number[] = [];
  rack.devices.forEach((d) => { if (d.position_u && d.u_height > 0) us.push(d.position_u, d.position_u + d.u_height - 1); });
  rack.planned.forEach((p) => us.push(p.position_u));
  if (!us.length) return [1, rack.u_height];
  return [Math.max(1, Math.min(...us) - 1), Math.min(rack.u_height, Math.max(...us) + 1)];
}

function Faceplate({ d, face }: { d: DeviceCard; face: Face }) {
  const ports = d.role === "switch" ? 12 : d.role === "patch_panel" ? 12 : 0;
  if (face === "rear" && (d.role === "server" || d.role === "switch")) {
    return (
      <div className="flex h-full items-center gap-1.5 px-2">
        {["PSU1", "PSU2"].map((p) => {
          const missing = d.power_findings.some((f) => f.code === "missing_power_connection" && f.message.startsWith(p));
          return (
            <span key={p} className={clsx("flex h-[13px] items-center gap-1 rounded-[3px] border px-1 font-mono text-[8.5px] leading-none",
              missing ? "border-dashed border-crit/70 text-crit" : "border-[#46536E] bg-[#232E45] text-[#B9C4D8]")}
              title={missing ? `${p}: no modeled PDU connection` : `${p}: connected (modeled)`}>
              <Zap className="h-2 w-2" aria-hidden />{p}{missing ? " ✕" : ""}
            </span>
          );
        })}
        <span className="ml-auto hidden gap-[2px] sm:flex" aria-hidden>
          {Array.from({ length: 4 }).map((_, i) => <span key={i} className="h-[7px] w-[9px] rounded-[1px] bg-[#0E1422] ring-1 ring-[#3A4762]" />)}
        </span>
      </div>
    );
  }
  if (ports) {
    return (
      <div className="flex h-full items-center gap-[3px] pl-14 pr-2" aria-hidden>
        {Array.from({ length: ports }).map((_, i) => (
          <span key={i} className={clsx("h-[7px] flex-1 rounded-[1.5px]", d.role === "patch_panel" ? "bg-[#0E1422] ring-1 ring-[#4A5A7A]" : "bg-[#0E1422] ring-1 ring-[#334160]")} />
        ))}
      </div>
    );
  }
  // server front: drive bays
  const bays = d.u_height >= 2 ? 12 : 8;
  return (
    <div className={clsx("grid h-full items-center gap-[2px] py-[3px] pl-[68px] pr-7", d.u_height >= 2 ? "grid-cols-6 grid-rows-2" : "grid-cols-8")} aria-hidden>
      {Array.from({ length: bays }).map((_, i) => <span key={i} className="h-full max-h-[11px] rounded-[1.5px] bg-gradient-to-b from-[#C9D2DE] to-[#AEB9C8] ring-1 ring-black/10" />)}
    </div>
  );
}

export function RackElevation({ rack, selected, onSelect, face = "front", compact = false, range }: {
  rack: Rack; selected?: string | null; onSelect?: (d: DeviceCard) => void; face?: Face; compact?: boolean; range?: [number, number];
}) {
  const [hover, setHover] = useState<string | null>(null);
  const uPx = compact ? 17 : U_PX;
  const lo = range?.[0] ?? 1;
  const hi = range?.[1] ?? rack.u_height;
  const units = hi - lo + 1;
  const height = units * uPx;
  const racked = rack.devices.filter((d) => d.position_u && d.u_height > 0);
  const pdus = rack.devices.filter((d) => d.role === "pdu");

  const occupied = useMemo(() => {
    const s = new Set<number>();
    racked.forEach((d) => { for (let u = d.position_u!; u < d.position_u! + d.u_height; u++) s.add(u); });
    rack.planned.forEach((p) => s.add(p.position_u));
    return s;
  }, [racked, rack.planned]);

  const freeRanges = useMemo(() => {
    const ranges: [number, number][] = [];
    let start: number | null = null;
    for (let u = lo; u <= hi + 1; u++) {
      const free = u <= hi && !occupied.has(u);
      if (free && start === null) start = u;
      if (!free && start !== null) { ranges.push([start, u - 1]); start = null; }
    }
    return ranges.filter(([a, b]) => b - a >= 2);
  }, [occupied, lo, hi]);

  const top = (u: number, h: number) => (hi - (u + h - 1)) * uPx;

  return (
    <figure className="relative select-none" aria-label={`Rack ${rack.display_id} ${face} elevation`}>
      <div className="relative mx-auto flex rounded-[14px] bg-gradient-to-b from-[#1A2438] to-[#111A2B] p-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.06),0_10px_30px_-12px_rgba(16,24,39,0.6)]">
        {/* U numbers left */}
        <div className="relative w-6 shrink-0" style={{ height }} aria-hidden>
          {Array.from({ length: units }).map((_, i) => {
            const u = hi - i;
            return <div key={u} className={clsx("absolute right-1 font-mono text-[8.5px] leading-none", u % 5 === 0 ? "text-[#8E9BB3]" : "text-[#4E5B75]")} style={{ top: i * uPx + uPx / 2 - 4 }}>{u}</div>;
          })}
        </div>
        {face === "rear" && <PduStrip pdus={pdus.filter((p) => p.display_id.endsWith("-a"))} height={height} side="left" />}
        <div className="rack-rail w-[5px] shrink-0 rounded-sm" style={{ height }} aria-hidden />
        <div className="relative flex-1 overflow-visible" style={{ height }}>
          {/* unit lines */}
          {Array.from({ length: units }).map((_, i) => (
            <div key={i} className="absolute inset-x-0 border-t border-white/[0.035]" style={{ top: i * uPx }} aria-hidden />
          ))}
          {freeRanges.map(([a, b]) => (
            <div key={a} className="absolute inset-x-1 flex items-center justify-center rounded-md border border-dashed border-white/[0.07] text-[9.5px] font-medium uppercase tracking-[0.14em] text-white/20"
              style={{ top: top(a, b - a + 1) + 2, height: (b - a + 1) * uPx - 4 }} aria-hidden>
              {b - a + 1}U free
            </div>
          ))}
          {rack.planned.map((p) => (
            <div key={p.intake} className="absolute inset-x-0.5 flex items-center gap-1.5 rounded-[4px] border border-dashed border-accent-300/70 bg-accent/10 px-2 text-[10px] text-accent-300"
              style={{ top: top(p.position_u, 1) + 1, height: uPx - 2 }} title={`Planned position for ${p.hostname} (${p.intake}), acceptance ${p.status.replace(/_/g, " ")}`}>
              <ClipboardCheck className="h-3 w-3 shrink-0" aria-hidden />
              <span className="truncate font-mono">{p.hostname}</span>
              <span className="ml-auto hidden truncate text-[9px] uppercase tracking-wider text-accent-300/80 sm:inline">planned · {p.status.replace(/_/g, " ")}</span>
            </div>
          ))}
          {racked.map((d, idx) => {
            const sel = selected === d.display_id;
            const inc = d.open_incidents.length;
            const h = d.u_height * uPx - 2;
            const isNet = d.role !== "server";
            return (
              <motion.button key={d.display_id} type="button" onClick={() => onSelect?.(d)}
                onMouseEnter={() => setHover(d.display_id)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(d.display_id)} onBlur={() => setHover(null)}
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2, delay: 0.02 * idx }}
                className={clsx("group absolute inset-x-0.5 overflow-hidden rounded-[4px] text-left outline-none transition-[box-shadow,filter] duration-150 hover:brightness-110",
                  isNet ? "bg-gradient-to-b from-[#2B3852] to-[#212C42] ring-1 ring-[#3A4762]" : "bg-gradient-to-b from-[#E7ECF2] to-[#CFD7E2] ring-1 ring-black/20",
                  sel && "ring-2 ring-accent-300 shadow-[0_0_0_4px_rgba(93,179,188,0.25)]",
                  d.health === "critical" && !sel && "ring-2 ring-[#FF5A67]/80",
                  "focus-visible:ring-2 focus-visible:ring-accent-300")}
                style={{ top: top(d.position_u!, d.u_height) + 1, height: h }}
                aria-label={`${d.display_id}, ${d.role.replace("_", " ")}, U${d.position_u}${d.u_height > 1 ? `–U${d.position_u! + d.u_height - 1}` : ""}, health ${d.health}${inc ? `, ${inc} open incident${inc > 1 ? "s" : ""}` : ""}`}
                aria-pressed={sel}>
                {/* ears */}
                <span className={clsx("absolute inset-y-0 left-0 w-[5px]", isNet ? "bg-[#1A2336]" : "bg-[#B8C2CF]")} aria-hidden />
                <span className={clsx("absolute inset-y-0 right-0 w-[5px]", isNet ? "bg-[#1A2336]" : "bg-[#B8C2CF]")} aria-hidden />
                <Faceplate d={d} face={face} />
                <span className={clsx("absolute left-2.5 top-1/2 flex -translate-y-1/2 items-center gap-1.5 font-mono text-[9.5px] font-semibold",
                  isNet ? "text-[#C9D3E3]" : "text-[#26324A]")}>
                  <span className={clsx("led h-[6px] w-[6px]", healthLed(d.health))} aria-hidden />
                  <span className={clsx(face === "front" && !isNet && "rounded-[2px] bg-[#E7ECF2]/90 px-0.5")}>{d.display_id.replace("nl-r01-", "")}</span>
                </span>
                {inc > 0 && (
                  <span className="absolute right-2 top-1/2 flex h-[14px] -translate-y-1/2 items-center gap-0.5 rounded-full bg-crit px-1.5 text-[9px] font-bold text-white shadow"
                    title={`${inc} open incident(s)`}>
                    <AlertTriangle className="h-2.5 w-2.5" aria-hidden />{inc}
                  </span>
                )}
                {!inc && d.power_findings.some((f) => f.severity === "critical") && (
                  <span className="absolute right-2 top-1/2 h-[12px] -translate-y-1/2 rounded-full border border-warn bg-warn-50 px-1 text-[8.5px] font-bold leading-[10px] text-warn" title="Documentation defect: power">PWR</span>
                )}
                {sel && <motion.span layoutId={`sel-${rack.display_id}`} className="pointer-events-none absolute inset-0 rounded-[4px] bg-accent-300/10" transition={{ duration: 0.2 }} />}
              </motion.button>
            );
          })}
        </div>
        <div className="rack-rail w-[5px] shrink-0 rounded-sm" style={{ height }} aria-hidden />
        {face === "rear" && <PduStrip pdus={pdus.filter((p) => !p.display_id.endsWith("-a"))} height={height} side="right" />}
      </div>
      {hover && (() => {
        const d = racked.find((x) => x.display_id === hover);
        if (!d) return null;
        return (
          <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.15 }}
            className="pointer-events-none absolute -bottom-2 left-1/2 z-20 w-max max-w-[260px] -translate-x-1/2 translate-y-full rounded-lg border border-line bg-white px-3 py-2 text-[11.5px] shadow-lift" role="tooltip">
            <div className="mono font-semibold text-ink">{d.display_id}</div>
            <div className="text-ink-2">{d.model} · U{d.position_u}{d.u_height > 1 ? `–${d.position_u! + d.u_height - 1}` : ""} · {d.health}</div>
            {d.serial && <div className="mono text-ink-3">{d.serial}</div>}
          </motion.div>
        );
      })()}
    </figure>
  );
}

function PduStrip({ pdus, height, side }: { pdus: DeviceCard[]; height: number; side: "left" | "right" }) {
  if (pdus.length === 0) return <div className="w-1" />;
  return (
    <div className={clsx("flex shrink-0 gap-1", side === "left" ? "mr-1" : "ml-1")} style={{ height }}>
      {pdus.map((p) => (
        <div key={p.display_id} className="relative flex w-[18px] flex-col items-center justify-start gap-[5px] rounded-[4px] bg-[#0E1422] py-2 ring-1 ring-[#3A4762]"
          title={`${p.display_id} (${p.model})`} aria-label={`PDU ${p.display_id}`}>
          <span className="mb-1 rotate-180 font-mono text-[8px] text-[#8E9BB3] [writing-mode:vertical-rl]">{p.display_id.replace(/^nl-r0\d-/, "")}</span>
          {Array.from({ length: 8 }).map((_, i) => <span key={i} className="h-[6px] w-[8px] rounded-[1px] bg-[#232E45] ring-1 ring-[#46536E]" />)}
        </div>
      ))}
    </div>
  );
}

export function RackTable({ rack }: { rack: Rack }) {
  const rows = [...rack.devices].sort((a, b) => (b.position_u ?? 0) - (a.position_u ?? 0));
  return (
    <table className="table">
      <caption className="sr-only">Contents of rack {rack.display_id}</caption>
      <thead><tr><th scope="col">Position</th><th scope="col">Device</th><th scope="col">Role</th><th scope="col">Health</th><th scope="col">Open incidents</th></tr></thead>
      <tbody>
        {rows.map((d) => (
          <tr key={d.display_id}>
            <td className="mono">{d.position_u ? `U${d.position_u}${d.u_height > 1 ? `–U${d.position_u + d.u_height - 1}` : ""}` : d.role === "pdu" ? "0U (rear)" : "—"}</td>
            <td className="mono">{d.display_id}</td><td>{d.role.replace("_", " ")}</td><td>{d.health}</td><td>{d.open_incidents.length || "None"}</td>
          </tr>
        ))}
        {rack.planned.map((p) => (
          <tr key={p.intake}><td className="mono">U{p.position_u}</td><td className="mono">{p.hostname} (planned)</td><td>server</td><td>Not installed</td><td>Acceptance: {p.status.replace(/_/g, " ")}</td></tr>
        ))}
      </tbody>
    </table>
  );
}
