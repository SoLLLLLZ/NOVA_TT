import { GPU_NOMINAL_GB } from "../config";
import type { Gpu } from "../api/types";

export function formatTokens(value: number): string {
  if (value >= 1024 && value % 1024 === 0) return `${value / 1024}K`;
  return value.toLocaleString("en-US");
}

export function formatRate(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return Math.round(value).toLocaleString("en-US");
}

/** "L40 · 48 GB" for a GPU type, using nominal size when known. */
export function gpuLabel(type: string, gpus: Gpu[] = []): string {
  const nominal = GPU_NOMINAL_GB[type];
  if (nominal) return `${type} · ${nominal} GB`;
  const mib = gpus.find((gpu) => gpu.label === type)?.memory_total_mib;
  return mib ? `${type} · ${Math.round(mib / 1024)} GB` : type;
}

/** Distinct GPU types available: allocated GPUs first, else what the models need. */
export function gpuTypes(gpus: Gpu[], modelTypes: string[]): string[] {
  const types = gpus.length ? gpus.map((gpu) => modelTypes.find((type) => gpu.name?.includes(type)) ?? gpu.label) : modelTypes;
  return [...new Set(types.filter(Boolean))];
}
