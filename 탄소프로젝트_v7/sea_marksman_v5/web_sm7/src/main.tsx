import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css";
import "@fontsource-variable/archivo/wdth.css";
import "./styles.css";
import "./styles6.css";
import "./styles7.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
