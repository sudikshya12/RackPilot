import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

export type StreamState = "connecting" | "live" | "reconnecting" | "offline";

const TOPIC_KEYS: Record<string, string[][]> = {
  incident: [["incidents"], ["incident"], ["overview"], ["demo"], ["racks"], ["metrics"]],
  probe: [["incident-series"], ["overview"], ["racks"], ["demo"], ["incident"]],
  simulation: [["demo"], ["scenarios"], ["overview"], ["incidents"], ["racks"], ["sim-runs"]],
  device: [["racks"], ["devices"], ["device"], ["overview"]],
  acceptance: [["intakes"], ["intake"], ["run"], ["runs"], ["overview"], ["demo"]],
  inventory: [["spares"], ["reservations"], ["txns"], ["overview"], ["demo"]],
  audit: [["overview"], ["audit"], ["device"], ["asset"], ["returns"], ["assets"], ["demo"]],
  demo: [["demo"]],
};

/** One shared EventSource. The browser resends Last-Event-ID on reconnect, so the server replays missed events. */
export function useEventStream(): { state: StreamState; lastEventAt: number | null } {
  const qc = useQueryClient();
  const [state, setState] = useState<StreamState>("connecting");
  const [lastEventAt, setLast] = useState<number | null>(null);
  const pending = useRef<Set<string>>(new Set());
  const timer = useRef<number | null>(null);

  useEffect(() => {
    let es: EventSource | null = null;
    let closed = false;
    let retry = 0;
    let lastId: string | null = null;

    const flush = () => {
      timer.current = null;
      for (const k of pending.current) qc.invalidateQueries({ queryKey: JSON.parse(k) });
      pending.current.clear();
    };
    const schedule = (topic: string) => {
      for (const key of TOPIC_KEYS[topic] ?? []) pending.current.add(JSON.stringify(key));
      if (timer.current === null) timer.current = window.setTimeout(flush, 120);
    };

    const connect = () => {
      if (closed) return;
      const url = lastId ? `/api/events?last_event_id=${encodeURIComponent(lastId)}` : "/api/events";
      es = new EventSource(url);
      es.onopen = () => { retry = 0; setState("live"); };
      es.onerror = () => {
        es?.close();
        if (closed) return;
        setState(retry > 2 ? "offline" : "reconnecting");
        retry += 1;
        window.setTimeout(connect, Math.min(1000 * 2 ** Math.min(retry, 4), 15000));
      };
      for (const topic of [...Object.keys(TOPIC_KEYS), "hello"]) {
        es.addEventListener(topic, (ev) => {
          const me = ev as MessageEvent;
          if (me.lastEventId) lastId = me.lastEventId;
          setLast(Date.now());
          if (topic !== "hello") schedule(topic);
        });
      }
    };
    connect();
    return () => { closed = true; es?.close(); if (timer.current) window.clearTimeout(timer.current); };
  }, [qc]);

  // Fallback: when the stream is not live (e.g. between serverless reconnects), poll the views that matter.
  useEffect(() => {
    if (state === "live") return;
    const keys = [["overview"], ["demo"], ["incidents"], ["incident"], ["racks"], ["intake"], ["run"], ["incident-series"]];
    const t = window.setInterval(() => keys.forEach((k) => qc.invalidateQueries({ queryKey: k })), 3000);
    return () => window.clearInterval(t);
  }, [state, qc]);

  return { state, lastEventAt };
}
