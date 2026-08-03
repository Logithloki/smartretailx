import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "react-oidc-context";
import { WebStorageStateStore } from "oidc-client-ts";

import App from "./App";
import { authConfig } from "./auth-config";
import "./styles.css";

/*
 * Auth stack rationale (react-oidc-context vs manual Cognito).
 *
 * Cognito's AWS SDK "Amplify Auth" pulls in ~200 KB of Amplify runtime
 * and shells out to Cognito's proprietary API for something that is
 * literally spec OpenID Connect. react-oidc-context is a thin React
 * wrapper around oidc-client-ts (~15 KB) and works with any spec-
 * compliant IdP - including a swap to Auth0 / Okta / self-hosted
 * Keycloak later without rewriting a single page component. The auth
 * flow is authorization code + PKCE (RFC 7636), which is the OAuth2
 * BCP for public SPAs.
 *
 * userStore is deliberately localStorage rather than the default
 * sessionStorage: closing the tab during a demo should not force
 * re-login. Tokens live only until Cognito's TTL (60 min access) so
 * this is not a persistence-forever situation.
 */

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider
      {...authConfig}
      userStore={new WebStorageStateStore({ store: window.localStorage })}
    >
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </AuthProvider>
  </React.StrictMode>,
);
