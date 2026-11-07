import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/press-start-2p/400.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/700.css";
import "@fontsource/silkscreen/400.css";
import "./styles/tokens.css";
import "./styles/app.css";
import { App } from "./App";
import { desktop } from "./lib/desktop";

if (desktop) document.documentElement.classList.add("is-desktop");

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
