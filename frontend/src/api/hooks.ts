import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import { api, ApiError } from "./client";
import { useToast } from "@/components/ui/Toast";
import type * as T from "./types";

const q = <D,>(key: unknown[], path: string, opts: Partial<UseQueryOptions<D>> = {}) =>
  // eslint-disable-next-line react-hooks/rules-of-hooks
  useQuery<D>({ queryKey: key, queryFn: () => api<D>(path), ...opts });

export const useOverview = () => q<any>(["overview"], "/overview", { refetchInterval: 15000 });
export const useRacks = () => q<T.Rack[]>(["racks"], "/racks");
export const useDevice = (id?: string | number | null) => q<T.DeviceDetail>(["device", String(id)], `/devices/${id}`, { enabled: !!id });
export const useIncidents = (params: string) => q<{ items: T.IncidentSummary[]; total: number }>(["incidents", params], `/incidents?${params}`);
export const useIncident = (id?: string) => q<T.IncidentDetail>(["incident", id], `/incidents/${id}`, { enabled: !!id });
export const useIncidentSeries = (id?: string) =>
  q<{ source_type: T.SourceType; series: { metric: string; value: number | null; unit: string; labels: Record<string, string>; observed_at: string; source_id: string }[] }>(
    ["incident-series", id], `/incidents/${id}/metrics-series`, { enabled: !!id });
export const useMetrics = () => q<T.AggregateMetrics>(["metrics"], "/incidents/metrics");
export const useScenarios = () => q<any[]>(["scenarios"], "/scenarios");
export const useRunbooks = () => q<any[]>(["runbooks"], "/runbooks");
export const useIntakes = () => q<T.Intake[]>(["intakes"], "/acceptance/intakes");
export const useIntake = (id?: string) => q<T.Intake>(["intake", id], `/acceptance/intakes/${id}`, { enabled: !!id });
export const useRun = (id?: string | number | null) => q<T.RunDetail>(["run", String(id)], `/acceptance/runs/${id}`, { enabled: !!id });
export const useRuns = () => q<T.RunSummary[]>(["runs"], "/acceptance/runs");
export const useProfiles = () => q<any[]>(["profiles"], "/acceptance/profiles");
export const useCollectorsAcc = () => q<any[]>(["acc-collectors"], "/acceptance/collectors");
export const useAssets = (params = "") => q<T.Asset[]>(["assets", params], `/assets?${params}`);
export const useAsset = (id?: string) => q<any>(["asset", id], `/assets/${id}`, { enabled: !!id });
export const useSpares = (deviceId?: number | null) =>
  q<{ device: T.DeviceRef | null; stock: T.Stock[] }>(["spares", deviceId ?? "all"], deviceId ? `/spares?device_id=${deviceId}` : "/spares");
export const useReservations = () => q<T.Reservation[]>(["reservations"], "/reservations");
export const useTxns = () => q<T.Txn[]>(["txns"], "/inventory/transactions?limit=100");
export const useReturns = () => q<T.ReturnRecord[]>(["returns"], "/returns");
export const useCables = () => q<T.Cable[]>(["cables"], "/cables");
export const useCableAudit = () => q<{ issues: any[] }>(["cable-audit"], "/cables/audit");
export const usePower = () => q<any>(["power"], "/power");
export const useAudit = (params = "") => q<{ items: T.AuditEvent[]; total: number }>(["audit", params], `/audit?${params}`);
export const useDemos = () => q<T.DemoStatus[]>(["demo"], "/demos");
export const useDemo = (key?: string | null) => q<T.DemoStatus>(["demo", key], `/demos/${key}`, { enabled: !!key });
export const useProfile = () => q<any>(["profile"], "/profile");
export const useSettings = () => q<any>(["settings"], "/settings");
export const useProjectResults = (slug: string) => q<any>(["project-results", slug], `/projects/${slug}/results`);
export const useSimRuns = () => q<any[]>(["sim-runs"], "/simulation/runs");

/** Mutation helper: shows a toast with the server's message on error, and invalidates everything on success. */
export function useAction<V = void, R = unknown>(fn: (v: V) => Promise<R>, opts: { success?: string | ((r: R) => string | undefined); onSuccess?: (r: R) => void } = {}) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation<R, ApiError, V>({
    mutationFn: fn,
    onSuccess: (r) => {
      qc.invalidateQueries();
      const msg = typeof opts.success === "function" ? opts.success(r) : opts.success;
      if (msg) toast.push({ tone: "ok", title: msg });
      opts.onSuccess?.(r);
    },
    onError: (e) => toast.push({ tone: "error", title: e.message, detail: e.code !== "http_error" ? e.code : undefined }),
  });
}
