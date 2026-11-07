// Product name is still a placeholder; change it here only.
export const APP_NAME = "TuneIt";

export const DEFAULT_API_BASE = "http://localhost:8000";

/** Contract major version this widget speaks; minor >= 1 adds GET /live. */
export const CONTRACT_MAJOR = 2;
export const LIVE_MIN_MINOR = 1;

export type ClusterOption = {
  id: string;
  name: string;
  note: string;
  /** target_id the backend advertises for this cluster, or null if not supported yet. */
  targetId: string | null;
};

// CMU GPU clusters students can reach. Only Wright has CANON evidence and a backend adapter.
export const CLUSTERS: ClusterOption[] = [
  { id: "wright", name: "Wright", note: "CMU · L40 · Slurm", targetId: "wright" },
  { id: "babel", name: "Babel", note: "LTI · not supported yet", targetId: null },
  { id: "bridges2", name: "Bridges-2", note: "PSC · not supported yet", targetId: null },
  { id: "flame", name: "FLAME", note: "H100 · not supported yet", targetId: null },
];

/** Marketing memory sizes; nvidia-smi reports slightly less usable MiB. */
export const GPU_NOMINAL_GB: Record<string, number> = {
  L40: 48,
  L40S: 48,
  A6000: 48,
  V100: 32,
  A100: 80,
  H100: 80,
};
