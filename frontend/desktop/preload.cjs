// Exposes the few desktop-only actions the widget UI needs.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("novaDesktop", {
  platform: process.platform,
  hide: () => ipcRenderer.send("widget:hide"),
});
