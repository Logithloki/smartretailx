import type { AuthProviderProps } from "react-oidc-context";

/*
 * Build-time config. Vite substitutes every import.meta.env.VITE_*
 * value into the bundle by literal string replacement during
 * `vite build`; there is no runtime lookup. See frontend/.env.example
 * for the trade-off write-up (client-side config endpoint vs build-
 * time bake).
 *
 * The values are consumed exactly once, at module load, so a broken
 * env fails fast (missing / undefined -> AuthProvider throws) rather
 * than silently redirecting to a wrong IdP.
 */
function required(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(
      `Missing required env var ${name}. Copy frontend/.env.example ` +
        `to frontend/.env and fill in every VITE_* value before ` +
        `running npm run dev or npm run build.`,
    );
  }
  return value;
}

export const API_BASE_URL = required(
  "VITE_API_BASE_URL",
  import.meta.env.VITE_API_BASE_URL,
);

export const authConfig: AuthProviderProps = {
  authority: required(
    "VITE_COGNITO_AUTHORITY",
    import.meta.env.VITE_COGNITO_AUTHORITY,
  ),
  client_id: required(
    "VITE_COGNITO_CLIENT_ID",
    import.meta.env.VITE_COGNITO_CLIENT_ID,
  ),
  redirect_uri: required(
    "VITE_COGNITO_REDIRECT_URI",
    import.meta.env.VITE_COGNITO_REDIRECT_URI,
  ),
  // "code" is the authorization-code flow. Combined with the automatic
  // PKCE support in oidc-client-ts this is the OAuth 2.0 BCP for
  // public SPAs (no client secret in the browser, code_verifier
  // proves possession, S256-hashed code_challenge sent on /authorize).
  response_type: "code",
  scope: "openid email profile",
  // Cognito silent-refresh needs an iframe on the same origin. We
  // point it at the SPA root; the response is intercepted before any
  // React code runs.
  automaticSilentRenew: true,
  // Loose PKCE guarantees code_verifier is generated per attempt.
  loadUserInfo: false,
  onSigninCallback: () => {
    // Remove ?code=... from the URL after a successful redirect back
    // from Cognito so a page refresh does not attempt to exchange the
    // consumed code again (Cognito rejects a code twice with an
    // opaque "invalid_grant" error).
    window.history.replaceState({}, document.title, window.location.pathname);
  },
};
