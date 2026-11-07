// Toolbar click opens the widget as a small standalone window that stays open
// while the student works in their terminal. A second click focuses it.

const WIDGET_URL = "widget.html";
const WINDOW_KEY = "widgetWindowId";
const SIZE = { width: 400, height: 820 };

async function existingWindow(): Promise<number | null> {
  const stored = await chrome.storage.session.get(WINDOW_KEY);
  const id = stored[WINDOW_KEY] as number | undefined;
  if (id === undefined) return null;
  try {
    await chrome.windows.get(id);
    return id;
  } catch {
    await chrome.storage.session.remove(WINDOW_KEY);
    return null;
  }
}

chrome.action.onClicked.addListener(async () => {
  const id = await existingWindow();
  if (id !== null) {
    await chrome.windows.update(id, { focused: true, drawAttention: true });
    return;
  }
  const created = await chrome.windows.create({
    url: chrome.runtime.getURL(WIDGET_URL),
    type: "popup",
    focused: true,
    ...SIZE,
  });
  if (created?.id !== undefined) await chrome.storage.session.set({ [WINDOW_KEY]: created.id });
});

chrome.windows.onRemoved.addListener(async (windowId) => {
  const stored = await chrome.storage.session.get(WINDOW_KEY);
  if (stored[WINDOW_KEY] === windowId) await chrome.storage.session.remove(WINDOW_KEY);
});
