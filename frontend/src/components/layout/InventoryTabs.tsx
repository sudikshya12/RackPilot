import clsx from "clsx";
import { NavLink } from "react-router-dom";

const TABS = [
  { to: "/assets", label: "Assets" },
  { to: "/spares", label: "Spare parts" },
  { to: "/returns", label: "Returns / RMA" },
];

/** Inventory section navigation. Each tab keeps its own direct URL. */
export function InventoryTabs() {
  return (
    <nav aria-label="Inventory" className="mb-5 flex gap-1 border-b border-line">
      {TABS.map((t) => (
        <NavLink key={t.to} to={t.to} className={({ isActive }) => clsx("-mb-px border-b-2 px-3 pb-2 pt-1 text-[13px] font-medium transition-colors",
          isActive ? "border-accent text-accent-700" : "border-transparent text-ink-2 hover:text-ink")}>{t.label}</NavLink>
      ))}
    </nav>
  );
}
