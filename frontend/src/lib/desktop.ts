// Present only inside the Electron desktop widget (see desktop/preload.cjs).
export type DesktopBridge = { platform: string; hide: () => void };

declare global {
  interface Window {
    novaDesktop?: DesktopBridge;
  }
}

export const desktop: DesktopBridge | undefined = typeof window !== "undefined" ? window.novaDesktop : undefined;
