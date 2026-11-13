import * as Dialog from "@radix-ui/react-dialog";
import { AnimatePresence, motion, useMotionValue, useReducedMotion, useSpring } from "framer-motion";
import { ArrowRight, Play, X } from "lucide-react";
import { Link } from "react-router-dom";
import { useCallback, useEffect, useRef, useState } from "react";
import type React from "react";

const SRC = "/media/rackops-tour.mp4";
const POSTER = "/media/rackops-tour-poster.jpg";
const CAPTIONS = "/media/rackops-tour.en.vtt";
const KEY = "rackops-tour-dismissed";

function readDismissed() {
  try { return localStorage.getItem(KEY) === "1"; } catch { return false; }
}

/** Shared state: whether the strip is dismissed, and the player's open state. */
export function useProductTour() {
  const [dismissed, setDismissed] = useState(readDismissed);
  const [open, setOpen] = useState(false);
  const dismiss = useCallback(() => {
    setDismissed(true);
    try { localStorage.setItem(KEY, "1"); } catch { /* storage unavailable */ }
  }, []);
  return { dismissed, dismiss, open, setOpen };
}

const TEASER = "/media/rackops-teaser.mp4";
const TEASER_POSTER = "/media/rackops-teaser-poster.jpg";
// Chapter start times inside the 12.6 s teaser loop (seconds).
const CHAPTERS: [string, number][] = [["Detect", 0], ["Investigate", 2.75], ["Verify", 5.1], ["Accept", 7.45], ["Trace", 10.0]];
const TEASER_LEN = 12.6;

function useChapter(video: React.RefObject<HTMLVideoElement>, enabled: boolean) {
  const [state, setState] = useState({ idx: 0, progress: 0 });
  useEffect(() => {
    if (!enabled) return;
    let raf = 0;
    const tick = () => {
      const t = video.current?.currentTime ?? 0;
      let idx = 0;
      CHAPTERS.forEach(([, s], i) => { if (t >= s) idx = i; });
      const start = CHAPTERS[idx][1];
      const end = idx + 1 < CHAPTERS.length ? CHAPTERS[idx + 1][1] : TEASER_LEN;
      setState((prev) => {
        const progress = Math.min(1, Math.max(0, (t - start) / (end - start)));
        return prev.idx === idx && Math.abs(prev.progress - progress) < 0.01 ? prev : { idx, progress };
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [video, enabled]);
  return state;
}

const HEAD_1 = ["Watch", "a", "failure"];
const HEAD_2 = ["become", "a", "verified", "recovery."];

/** Cinematic homepage hero: live muted preview, animated copy, opens the full film. */
export function ProductTourHero({ onPlay, onDismiss, playerOpen }: { onPlay: () => void; onDismiss: () => void; playerOpen: boolean }) {
  const reduce = useReducedMotion();
  const video = useRef<HTMLVideoElement>(null);
  const frame = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(true);
  const chapter = useChapter(video, !reduce);

  // 3D tilt toward the pointer, softened with springs.
  const rx = useSpring(useMotionValue(0), { stiffness: 140, damping: 18 });
  const ry = useSpring(useMotionValue(0), { stiffness: 140, damping: 18 });
  const onMove = (e: React.MouseEvent) => {
    if (reduce || !frame.current) return;
    const r = frame.current.getBoundingClientRect();
    ry.set(((e.clientX - r.left) / r.width - 0.5) * 9);
    rx.set(-((e.clientY - r.top) / r.height - 0.5) * 7);
  };
  const onLeave = () => { rx.set(0); ry.set(0); };

  // Only play the preview while it is on screen and the full film is closed.
  useEffect(() => {
    const el = frame.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { threshold: 0.2 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  useEffect(() => {
    const v = video.current;
    if (!v || reduce) return;
    if (visible && !playerOpen) v.play().catch(() => { /* autoplay blocked: poster stays */ });
    else v.pause();
  }, [visible, playerOpen, reduce]);

  const word = (w: string, i: number, base: number, cls = "") => (
    <motion.span key={`${w}${i}`} className={`inline-block ${cls}`} initial={{ opacity: 0, y: 18, filter: "blur(6px)" }}
      animate={{ opacity: 1, y: 0, filter: "blur(0px)" }} transition={{ duration: 0.5, delay: base + i * 0.07, ease: [0.2, 0.8, 0.2, 1] }}>
      {w}&nbsp;
    </motion.span>
  );

  return (
    <motion.section initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, height: 0, marginBottom: 0 }}
      transition={{ duration: 0.35, ease: [0.2, 0.8, 0.2, 1] }} aria-label="Product tour"
      className="dark-surface relative isolate overflow-hidden rounded-2xl border border-white/[0.07] bg-[#0B1322] text-white shadow-[0_24px_60px_-28px_rgba(8,127,140,0.55)]">
      {/* drifting aurora light */}
      <div className="pointer-events-none absolute inset-0 -z-10" aria-hidden>
        <span className="aurora absolute -left-24 -top-32 h-[420px] w-[520px] rounded-full bg-[#087F8C]/35 blur-[90px]" />
        <span className="aurora aurora-2 absolute -bottom-40 left-1/3 h-[380px] w-[520px] rounded-full bg-[#5B4BA8]/30 blur-[100px]" />
        <span className="aurora aurora-3 absolute -right-20 top-0 h-[360px] w-[420px] rounded-full bg-[#5DB3BC]/20 blur-[90px]" />
        <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/25 to-transparent" />
      </div>

      <div className="grid grid-cols-1 items-center gap-7 p-5 sm:p-7 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:gap-10 lg:p-9">
        <div className="min-w-0">
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
            className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.05] px-3 py-1 text-[11.5px] font-semibold uppercase tracking-[0.14em] text-accent-300">
            <span className="relative flex h-2 w-2" aria-hidden>
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent-300 opacity-60 motion-reduce:hidden" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-accent-300" />
            </span>
            Product tour · 1:10
          </motion.div>
          <h2 className="mt-4 text-[30px] font-semibold leading-[1.08] tracking-[-0.025em] sm:text-[38px] xl:text-[44px]">
            <span className="block">{HEAD_1.map((w, i) => word(w, i, 0.1))}</span>
            <span className="block">{HEAD_2.map((w, i) => word(w, i, 0.32, "bg-gradient-to-r from-white via-[#B9E4E8] to-accent-300 bg-clip-text text-transparent"))}</span>
          </h2>
          <motion.p initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.7 }}
            className="mt-4 max-w-[460px] text-[14.5px] leading-relaxed text-[#A9B6CA]">
            See the real app in 70 seconds: a failed service tracked to a verified fix, a server rejected and re-tested, and a repair that reconciles inventory.
          </motion.p>
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.85 }} className="mt-6 flex flex-wrap items-center gap-3">
            <button onClick={onPlay}
              className="group inline-flex h-11 items-center gap-2.5 rounded-full bg-white pl-1.5 pr-5 text-[14px] font-semibold text-nav shadow-[0_10px_30px_-10px_rgba(93,179,188,0.8)] transition-transform duration-200 hover:scale-[1.03] active:scale-[0.99]">
              <span className="grid h-8 w-8 place-items-center rounded-full bg-accent text-white transition-colors group-hover:bg-accent-700"><Play className="ml-0.5 h-3.5 w-3.5 fill-current" aria-hidden /></span>
              Watch the film
              <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-1" aria-hidden />
            </button>
            <Link to="/demo" className="inline-flex h-11 items-center rounded-full border border-white/15 px-5 text-[14px] font-medium text-white/90 transition-colors hover:border-white/30 hover:bg-white/[0.06]">
              Run live demo
            </Link>
          </motion.div>
          <motion.ol initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.05, duration: 0.5 }}
            className="mt-7 flex flex-wrap gap-x-4 gap-y-2" aria-label="Film chapters">
            {CHAPTERS.map(([name], i) => {
              const active = !reduce && chapter.idx === i;
              return (
                <li key={name} className="min-w-[64px]">
                  <span className={`text-[12px] font-medium transition-colors duration-300 ${active ? "text-white" : "text-white/45"}`}>{name}</span>
                  <span className="mt-1 block h-[2px] overflow-hidden rounded-full bg-white/10" aria-hidden>
                    <span className="block h-full rounded-full bg-accent-300" style={{ width: active ? `${chapter.progress * 100}%` : chapter.idx > i && !reduce ? "100%" : "0%", opacity: active ? 1 : 0.35 }} />
                  </span>
                </li>
              );
            })}
          </motion.ol>
        </div>

        <div className="min-w-0 [perspective:1400px]">
          <motion.div ref={frame} onMouseMove={onMove} onMouseLeave={onLeave} style={{ rotateX: rx, rotateY: ry }}
            initial={{ opacity: 0, y: 24, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.7, delay: 0.2, ease: [0.2, 0.8, 0.2, 1] }}
            className="relative">
            <div className={reduce ? "" : "hero-float"}>
              <button onClick={onPlay} aria-label="Play the 70-second product tour with sound"
                className="group relative block w-full overflow-hidden rounded-xl text-left ring-1 ring-white/15 shadow-[0_40px_80px_-30px_rgba(0,0,0,0.9),0_0_0_1px_rgba(93,179,188,0.08)] focus-visible:outline-offset-4">
                <video ref={video} className="block aspect-[1140/670] w-full bg-[#0B1322] object-cover transition-transform duration-700 ease-out group-hover:scale-[1.025]"
                  src={TEASER} poster={TEASER_POSTER} muted loop playsInline preload="auto" aria-hidden tabIndex={-1} />
                <span className="pointer-events-none absolute inset-0 bg-gradient-to-t from-[#0B1322]/75 via-transparent to-transparent" aria-hidden />
                <span className="hero-sheen pointer-events-none absolute inset-0" aria-hidden />
                <span className="absolute inset-0 grid place-items-center" aria-hidden>
                  <span className="relative grid place-items-center">
                    {!reduce && <><span className="hero-ring absolute h-20 w-20 rounded-full border border-white/50" /><span className="hero-ring hero-ring-2 absolute h-20 w-20 rounded-full border border-white/40" /></>}
                    <span className="grid h-[72px] w-[72px] place-items-center rounded-full bg-white/95 text-nav shadow-[0_12px_40px_-8px_rgba(0,0,0,0.6)] backdrop-blur transition-transform duration-300 group-hover:scale-110">
                      <Play className="ml-1 h-7 w-7 fill-current" />
                    </span>
                  </span>
                </span>
                <span className="absolute bottom-3 left-3 inline-flex items-center gap-1.5 rounded-full bg-black/45 px-2.5 py-1 text-[11px] font-medium text-white/85 backdrop-blur" aria-hidden>
                  <span className="h-1.5 w-1.5 rounded-full bg-[#FF5A67]" />Preview · muted
                </span>
                <span className="absolute bottom-3 right-3 rounded-full bg-black/45 px-2.5 py-1 text-[11px] font-medium text-white/85 backdrop-blur" aria-hidden>Watch with sound · 1:10</span>
              </button>
            </div>
          </motion.div>
        </div>
      </div>
      <button onClick={onDismiss} className="absolute right-3 top-3 rounded-full p-1.5 text-white/50 transition-colors hover:bg-white/10 hover:text-white" aria-label="Dismiss product tour">
        <X className="h-4 w-4" />
      </button>
    </motion.section>
  );
}

/** Cinematic lightbox player. The video loads only when opened. */
export function ProductTourPlayer({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => { ref.current?.play().catch(() => { /* autoplay blocked: controls remain */ }); }, 250);
    return () => window.clearTimeout(t);
  }, [open]);
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open && (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild forceMount>
              <motion.div className="fixed inset-0 z-[90] bg-[#05080F]/90 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }} />
            </Dialog.Overlay>
            <Dialog.Content forceMount aria-describedby={undefined}
              className="fixed inset-0 z-[91] grid place-items-center p-4 outline-none"
              onClick={(e) => { if (e.target === e.currentTarget) onOpenChange(false); }}>
              <motion.div className="w-[min(1120px,100%)]"
                initial={{ opacity: 0, scale: 0.97, y: 8 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.98 }} transition={{ duration: 0.22, ease: [0.2, 0.8, 0.2, 1] }}>
                <div className="mb-2.5 flex items-center justify-between px-1">
                  <Dialog.Title className="text-[13px] font-medium text-white/90">RackOps Lab · Product tour</Dialog.Title>
                  <Dialog.Close className="rounded-md p-1.5 text-white/70 transition-colors hover:bg-white/10 hover:text-white" aria-label="Close video"><X className="h-5 w-5" /></Dialog.Close>
                </div>
                <div className="overflow-hidden rounded-xl bg-black shadow-[0_30px_80px_-20px_rgba(8,127,140,0.35),0_20px_60px_-10px_rgba(0,0,0,0.8)] ring-1 ring-white/10">
                  <video ref={ref} className="block aspect-video max-h-[calc(100vh-9rem)] w-full" controls playsInline preload="metadata" poster={POSTER}>
                    <source src={SRC} type="video/mp4" />
                    <track kind="captions" src={CAPTIONS} srcLang="en" label="English" default />
                  </video>
                </div>
                <p className="mt-2.5 px-1 text-[11.5px] text-white/50">Demonstrated with simulated lab data · captions available</p>
              </motion.div>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}
