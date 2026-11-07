// CMUTuneIt desktop widget: a small frameless window that floats above other apps,
// can be dragged anywhere, and toggles with Option+Space or the menu-bar icon.
//
//   npm run desktop        build the UI, then open the widget
//   npm run desktop:dev    use the running Vite dev server (npm run dev) instead

const { app, BrowserWindow, Menu, Tray, globalShortcut, ipcMain, nativeImage, net, protocol, screen } = require("electron");
const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { pathToFileURL } = require("node:url");

const SHORTCUT = "Alt+Space";
const SIZE = { width: 380, height: 740 };
const MARGIN = 24;
const DIST = path.join(__dirname, "..", "dist");
const DEV_URL = process.env.NOVA_DEV_URL;
const APP_ORIGIN = "app://widget";
const PROJECT_ROOT = process.env.NOVA_PROJECT_ROOT || (app.isPackaged
  ? JSON.parse(fs.readFileSync(path.join(process.resourcesPath, "nova-project.json"), "utf8")).root
  : path.resolve(__dirname, "../.."));
const STATE = process.env.NOVA_STATE_DIR || path.join(PROJECT_ROOT, "var/backend");
const API = "http://127.0.0.1:8000";
fs.mkdirSync(path.join(PROJECT_ROOT, "var/desktop"), { recursive: true, mode: 0o700 });
app.setName("TuneIt");
app.setPath("userData", path.join(PROJECT_ROOT, "var/desktop"));
let backend = null;
let connection = null;

async function startBackend() {
  const healthy = async () => {
    try {
      const response = await fetch(API + "/health", { signal: AbortSignal.timeout(1000) });
      const data = await response.json();
      return response.ok && data.contract_version === "2.1" && !data.simulation;
    } catch { return false; }
  };
  if (!(await healthy())) {
    const logfile = fs.openSync(path.join(PROJECT_ROOT, "var/desktop/backend.log"), "a", 0o600);
    backend = spawn(path.join(PROJECT_ROOT, ".venv/bin/python"),
      ["-m", "uvicorn", "nova_backend.app:app", "--host", "127.0.0.1", "--port", "8000", "--workers", "1"],
      { cwd: PROJECT_ROOT, env: { ...process.env, NOVA_MODE: "wright", NOVA_STATE_DIR: STATE }, stdio: ["ignore", logfile, logfile] });
    fs.closeSync(logfile);
    let launchError = null;
    backend.on("error", (error) => { launchError = error; });
    for (let i = 0; i < 120; i++) {
      if (launchError || backend.exitCode !== null) throw new Error("Backend could not start. See var/desktop/backend.log.");
      if (await healthy()) break;
      await new Promise(resolve => setTimeout(resolve, 250));
    }
    if (!(await healthy())) throw new Error("Backend startup timed out. See var/desktop/backend.log.");
  }
  // Only the local pairing token reaches our sandboxed renderer. Never read the OpenRouter key here.
  const token = fs.readFileSync(path.join(STATE, "pairing-token"), "utf8").trim();
  const status = await fetch(API + "/status", { headers: { "X-Pairing-Token": token }, signal: AbortSignal.timeout(15000) });
  if (!status.ok) throw new Error("The backend on port 8000 does not match this project's pairing file.");
  return { base: API, token };
}

let win = null;
let tray = null;

protocol.registerSchemesAsPrivileged([
  { scheme: "app", privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true } },
]);

if (!app.requestSingleInstanceLock()) app.exit(0);

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
  win.webContents.on("will-navigate", (event, url) => {
    if (!(url.startsWith(APP_ORIGIN + "/") || (DEV_URL && url === DEV_URL))) event.preventDefault();
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
    if (new URL(request.url).host !== "widget" || !file.startsWith(DIST + path.sep)) return new Response("Not found", { status: 404 });
    return net.fetch(pathToFileURL(file).toString());
  });

  connection = startBackend();
  connection.catch(() => {}); // forwarded as a visible connection error by the IPC handler
  ipcMain.handle("backend:connection", (event) => {
    const source = event.senderFrame?.url ?? "";
    if (event.sender !== win?.webContents || !(source.startsWith(APP_ORIGIN + "/") || (DEV_URL && source === DEV_URL))) {
      throw new Error("Untrusted widget sender");
    }
    return connection;
  });
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
  if (backend && backend.exitCode === null) backend.kill("SIGTERM");
});
app.on("will-quit", () => globalShortcut.unregisterAll());
app.on("window-all-closed", () => {
  /* stay alive in the menu bar */
});
