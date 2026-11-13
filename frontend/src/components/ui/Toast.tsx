import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

type Tone = "ok" | "error" | "info";
interface Toast { id: number; tone: Tone; title: string; detail?: string }
const Ctx = createContext<{ push: (t: Omit<Toast, "id">) => void }>({ push: () => {} });

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs.slice(-3), { ...t, id }]);
    window.setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), t.tone === "error" ? 7000 : 3800);
  }, []);
  const value = useMemo(() => ({ push }), [push]);
  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="fixed right-4 top-16 z-[80] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2" role="region" aria-label="Notifications" aria-live="polite">
        <AnimatePresence initial={false}>
          {items.map((t) => (
            <motion.div key={t.id} layout initial={{ opacity: 0, y: -10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, x: 24, transition: { duration: 0.15 } }} transition={{ duration: 0.2, ease: [0.2, 0.8, 0.2, 1] }}
              className={`flex items-start gap-2.5 rounded-xl border bg-white p-3 pr-2 shadow-lift ${t.tone === "error" ? "border-crit-100" : t.tone === "ok" ? "border-ok-100" : "border-line"}`}
              role={t.tone === "error" ? "alert" : "status"}>
              {t.tone === "error" ? <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-crit" aria-hidden /> :
                t.tone === "ok" ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-ok" aria-hidden /> : <Info className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden />}
              <div className="min-w-0 flex-1 text-[13px]">
                <div className="font-medium text-ink">{t.title}</div>
                {t.detail && <div className="mono mt-0.5 text-ink-2">{t.detail}</div>}
              </div>
              <button className="rounded p-1 text-ink-3 hover:bg-canvas hover:text-ink" onClick={() => setItems((xs) => xs.filter((x) => x.id !== t.id))} aria-label="Dismiss notification">
                <X className="h-3.5 w-3.5" />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </Ctx.Provider>
  );
}
export const useToast = () => useContext(Ctx);
