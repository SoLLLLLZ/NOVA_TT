// CMUTuneIt desktop widget: a small frameless window that floats above other apps,
// can be dragged anywhere, and toggles with Option+Space or the menu-bar icon.
//
//   npm run desktop        build the UI, then open the widget
//   npm run desktop:dev    use the running Vite dev server (npm run dev) instead

const { app, BrowserWindow, Menu, Tray, globalShortcut, ipcMain, nativeImage, net, protocol, screen, session } = require("electron");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const SHORTCUT = "Alt+Space";
const SIZE = { width: 380, height: 740 };
const MARGIN = 24;
const DIST = path.join(__dirname, "..", "dist");
const DEV_URL = process.env.NOVA_DEV_URL;
const APP_ORIGIN = "app://widget";
// The backend's CORS list includes the Vite dev origin; the widget presents as it.
const BACKEND_ORIGIN = "http://localhost:5173";
const BACKEND_URLS = ["*://localhost/*", "*://127.0.0.1/*"];

let win = null;
let tray = null;

protocol.registerSchemesAsPrivileged([
  { scheme: "app", privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true } },
]);

if (!app.requestSingleInstanceLock()) app.quit();

// ------------------------------------------------------------ window position
const stateFile = () => path.join(app.getPath("userData"), "window-state.json");

function savedPosition() {
  try {
    const { x, y } = JSON.parse(fs.readFileSync(stateFile(), "utf8"));
    const visible = screen.getAllDisplays().some(({ workArea: a }) =>
      x >= a.x && y >= a.y && x + 40 <= a.x + a.width && y + 40 <= a.y + a.height);
    return visible ? { x, y } : null;
  } catch {
    return null;
  }
}

function defaultPosition() {
  const { workArea } = screen.getPrimaryDisplay();
  return { x: workArea.x + workArea.width - SIZE.width - MARGIN, y: workArea.y + MARGIN };
}

function savePosition() {
  if (!win) return;
  const [x, y] = win.getPosition();
  try {
    fs.writeFileSync(stateFile(), JSON.stringify({ x, y }));
  } catch {
    /* position memory is a convenience */
  }
}

// ------------------------------------------------------------------- window
function createWindow() {
  const { x, y } = savedPosition() ?? defaultPosition();
  win = new BrowserWindow({
    ...SIZE,
    x,
    y,
    show: false,
    frame: false,
    transparent: true,
    backgroundColor: "#00000000",
    resizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    hasShadow: true,
    title: "CMUTuneIt",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });
  win.setAlwaysOnTop(true, "floating");
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

  win.loadURL(DEV_URL ?? `${APP_ORIGIN}/widget.html`);
  win.once("ready-to-show", () => showWidget());
  win.on("moved", savePosition);
  // Closing hides: the widget keeps running for the shortcut and menu-bar icon.
  win.on("close", (event) => {
    if (!app.isQuitting) {
      event.preventDefault();
      win.hide();
    }
  });
  // Links never open inside the widget.
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
}

function showWidget() {
  if (!win) return;
  win.show();
  win.focus();
}

function toggleWidget() {
  if (!win) return;
  if (win.isVisible() && win.isFocused()) win.hide();
  else showWidget();
}

// -------------------------------------------------------------- backend CORS
// The backend allows the Vite dev origin; requests from the packaged widget
// carry app://widget, so present the allowed origin and accept the answer.
function bridgeBackendCors() {
  if (DEV_URL) return; // the dev server already is that origin
  const filter = { urls: BACKEND_URLS };
  session.defaultSession.webRequest.onBeforeSendHeaders(filter, (details, callback) => {
    const headers = { ...details.requestHeaders };
    if (headers.Origin === APP_ORIGIN) headers.Origin = BACKEND_ORIGIN;
    callback({ requestHeaders: headers });
  });
  session.defaultSession.webRequest.onHeadersReceived(filter, (details, callback) => {
    const headers = {};
    for (const [name, value] of Object.entries(details.responseHeaders ?? {})) {
      if (name.toLowerCase() !== "access-control-allow-origin") headers[name] = value;
    }
    headers["Access-Control-Allow-Origin"] = [APP_ORIGIN];
    callback({ responseHeaders: headers });
  });
}

// --------------------------------------------------------------------- tray
function createTray() {
  const icon = nativeImage.createFromPath(path.join(__dirname, "..", "public", "icons", "icon-32.png")).resize({ width: 18, height: 18 });
  tray = new Tray(icon);
  tray.setToolTip("CMUTuneIt (⌥Space)");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Show / hide CMUTuneIt", accelerator: SHORTCUT, click: toggleWidget },
      { label: "Move to top-right corner", click: () => win?.setPosition(defaultPosition().x, defaultPosition().y) },
      { type: "separator" },
      { label: "Quit CMUTuneIt", click: () => { app.isQuitting = true; app.quit(); } },
    ]),
  );
}

// ---------------------------------------------------------------- lifecycle
app.whenReady().then(() => {
  if (process.platform === "darwin") app.dock?.hide();

  protocol.handle("app", (request) => {
    const { pathname } = new URL(request.url);
    const file = path.normalize(path.join(DIST, decodeURIComponent(pathname)));
    if (!file.startsWith(DIST)) return new Response("Not found", { status: 404 });
    return net.fetch(pathToFileURL(file).toString());
  });

  bridgeBackendCors();
  createWindow();
  createTray();

  if (!globalShortcut.register(SHORTCUT, toggleWidget)) {
    console.warn(`CMUTuneIt: ${SHORTCUT} is taken by another app; use the menu-bar icon instead.`);
  }

  ipcMain.on("widget:hide", () => win?.hide());
});

app.on("second-instance", showWidget);
app.on("activate", showWidget);
app.on("before-quit", () => {
  app.isQuitting = true;
});
app.on("will-quit", () => globalShortcut.unregisterAll());
app.on("window-all-closed", () => {
  /* stay alive in the menu bar */
});
