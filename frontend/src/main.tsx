import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, Config } from "./api";
import { Inbox } from "./Inbox";
import { Review } from "./Review";
import { MetricsView } from "./Metrics";
import "./styles.css";

function useHashRoute(): string {
  const [hash, setHash] = useState(window.location.hash || "#/");
  useEffect(() => {
    const on = () => setHash(window.location.hash || "#/");
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return hash;
}

function App() {
  const route = useHashRoute();
  const [config, setConfig] = useState<Config | null>(null);
  useEffect(() => {
    api.config().then(setConfig).catch(() => setConfig(null));
  }, []);

  const docMatch = route.match(/^#\/doc\/(\d+)/);
  const tab = docMatch ? "inbox" : route.startsWith("#/metrics") ? "metrics" : "inbox";

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <span className="mark" aria-hidden>¶</span>
          <span>Notebook to data</span>
        </div>
        <nav>
          <a href="#/" className={tab === "inbox" ? "on" : ""}>Pages</a>
          <a href="#/metrics" className={tab === "metrics" ? "on" : ""}>Accuracy &amp; cost</a>
        </nav>
        {config && (
          <span className={`engine ${config.extractor === "mock" ? "mock" : ""}`} title="Extractor in use">
            {config.extractor === "mock" ? "mock extractor (no API key)" : config.extractor}
          </span>
        )}
      </header>
      <main>
        {docMatch ? <Review key={docMatch[1]} id={Number(docMatch[1])} /> : tab === "metrics" ? <MetricsView /> : <Inbox />}
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
