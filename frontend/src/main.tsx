import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/pixelify-sans/500.css";
import "@fontsource/pixelify-sans/700.css";
import "@fontsource/silkscreen/400.css";
import "@fontsource/vt323/400.css";
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
