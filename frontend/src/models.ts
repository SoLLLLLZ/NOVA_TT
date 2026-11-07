import byteshapeCar from "./assets/cars/qwen3.8-27b.png";
import flashCar from "./assets/cars/qwen3.8-flash-next.png";
import glimmerCar from "./assets/cars/muse-glimmer.png";

export type CarPalette = {
  body: string;
  dark: string;
  accent: string;
  stripe: string;
  rim: string;
};

export type ModelLook = {
  /** Dropdown name from the UX brief; the backend display_name is the fallback. */
  name: string;
  car: string;
  /** Button fill and highlights follow the car's livery. */
  accent: string;
  accentInk: string;
  side: CarPalette;
};

export const MODEL_LOOKS: Record<string, ModelLook> = {
  "qwen3.8-27b": {
    name: "ByteShape Qwen3.8 27B",
    car: byteshapeCar,
    accent: "#C6F432",
    accentInk: "#0B1405",
    side: { body: "#B9E52C", dark: "#1D2329", accent: "#2A3139", stripe: "#1D2329", rim: "#C6F432" },
  },
  "qwen3.8-flash-next": {
    name: "Qwen3.8 Flash Next",
    car: flashCar,
    accent: "#5CE1FF",
    accentInk: "#04131F",
    side: { body: "#EEF5FF", dark: "#16305A", accent: "#2FB8F0", stripe: "#2FB8F0", rim: "#2FB8F0" },
  },
  "muse-glimmer": {
    name: "Muse Glimmer",
    car: glimmerCar,
    accent: "#FF9F8A",
    accentInk: "#25101A",
    side: { body: "#8B5AD6", dark: "#2B1C40", accent: "#FF9F8A", stripe: "#FFE7CC", rim: "#FF9F8A" },
  },
};

export function lookFor(modelId: string, displayName?: string): ModelLook {
  return MODEL_LOOKS[modelId] ?? { ...MODEL_LOOKS["qwen3.8-27b"], name: displayName ?? modelId };
}
