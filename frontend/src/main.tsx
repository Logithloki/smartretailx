import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { SmartRetailAuthProvider } from "./context/AuthContext";
import { CartProvider } from "./context/CartContext";
import { loadRuntimeConfig } from "./config/runtime-config";

import App from "./App";
import "./styles.css";

const root = ReactDOM.createRoot(document.getElementById("root")!);

function renderConfigurationError(error: unknown): void {
  const message = error instanceof Error ? error.message : String(error);
  root.render(
    <main className="loading-screen" role="alert">
      <h1>SmartRetailX configuration error</h1>
      <p>{message}</p>
    </main>,
  );
}

async function bootstrap(): Promise<void> {
  const config = await loadRuntimeConfig();
  root.render(
    <React.StrictMode>
      <SmartRetailAuthProvider config={config}>
        <CartProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </CartProvider>
      </SmartRetailAuthProvider>
    </React.StrictMode>,
  );
}

void bootstrap().catch(renderConfigurationError);
