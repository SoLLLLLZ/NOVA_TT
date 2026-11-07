// chrome.storage.local when running as the extension, localStorage in `npm run dev`.
// Every access is wrapped: storage can be unavailable and the widget must still work.

const hasChromeStorage = () => typeof chrome !== "undefined" && !!chrome.storage?.local;

export async function load<T>(key: string): Promise<T | null> {
  try {
    if (hasChromeStorage()) {
      const items = await chrome.storage.local.get(key);
      return (items[key] as T | undefined) ?? null;
    }
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export async function save(key: string, value: unknown): Promise<void> {
  try {
    if (hasChromeStorage()) await chrome.storage.local.set({ [key]: value });
    else window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* non-essential */
  }
}

export async function remove(key: string): Promise<void> {
  try {
    if (hasChromeStorage()) await chrome.storage.local.remove(key);
    else window.localStorage.removeItem(key);
  } catch {
    /* non-essential */
  }
}

export const KEYS = {
  pairing: "nova.pairingToken",
  apiBase: "nova.apiBase",
  tuned: "nova.tunedResult",
  pendingRun: "nova.pendingRun",
} as const;
