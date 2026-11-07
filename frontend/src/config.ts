// Product name is still a placeholder; change it here only.
export const APP_NAME = "CMUTuneIt";

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

// Publicly documented CMU / CMU-affiliated compute resources, not access entitlements.
// Only Wright has a backend adapter; null targets are disabled future integrations.
// Source inventory and exclusions: docs/research/CMU_CLUSTERS.md.
export const CLUSTERS: ClusterOption[] = [
  {"id": "wright", "name": "Wright", "note": "CMU · L40 · Slurm", "targetId": "wright"},
  {"id": "arjuna", "name": "Arjuna", "note": "Engineering · GPU/HPC · Future integration", "targetId": null},
  {"id": "atlas", "name": "Atlas (LTI)", "note": "LTI · HPC · Future integration", "targetId": null},
  {"id": "babel", "name": "Babel", "note": "LTI · GPU/HPC · Future integration", "targetId": null},
  {"id": "boston", "name": "Boston (LTI)", "note": "LTI · HPC · Future integration", "targetId": null},
  {"id": "bridges2", "name": "Bridges-2", "note": "PSC · GPU/HPC · Future integration", "targetId": null},
  {"id": "caps", "name": "CAPS", "note": "Atmospheric modeling · CPU HPC · Future integration", "targetId": null},
  {"id": "ece-dsc", "name": "ECE Data Science Cloud", "note": "ECE · GPU/CPU compute · Future integration", "targetId": null},
  {"id": "ece-number", "name": "ECE Number Cluster", "note": "ECE · GPU host pool · Future integration", "targetId": null},
  {"id": "euler", "name": "Euler", "note": "Physics · GPU/HPC · Future integration", "targetId": null},
  {"id": "ghc", "name": "GHC GPU pool", "note": "Gates · Course GPU workstations · Future integration", "targetId": null},
  {"id": "math-physics", "name": "Math/Physics Parallel Cluster", "note": "Math + Physics · GPU/CPU · Future integration", "targetId": null},
  {"id": "mind", "name": "MIND", "note": "NI/CNBC · GPU/HPC · Future integration", "targetId": null},
  {"id": "mld-gpu", "name": "MLD GPU resource", "note": "MLD · Department GPU resource · Future integration", "targetId": null},
  {"id": "neocortex", "name": "Neocortex", "note": "PSC · Cerebras AI · Future integration", "targetId": null},
  {"id": "orchard", "name": "ORCHARD (FLAME / Community)", "note": "CMU · Cloud GPUs · Future integration", "targetId": null},
  {"id": "qcd", "name": "QCD", "note": "Physics · CPU HPC · Future integration", "targetId": null},
  {"id": "trace", "name": "TRACE", "note": "Engineering / PSC · GPU/HPC · Future integration", "targetId": null},
  {"id": "vera", "name": "Vera", "note": "McWilliams / PSC · GPU/HPC · Future integration", "targetId": null},
  {"id": "bridges3", "name": "Bridges-3 (planned)", "note": "PSC · Planned 2027 · Future integration", "targetId": null},
  {"id": "tanglelab", "name": "TangleLab (planned)", "note": "PSC · Planned QPU + GPU system · Future integration", "targetId": null},
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
