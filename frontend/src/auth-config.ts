import { WebStorageStateStore } from "oidc-client-ts";
import type { AuthProviderNoUserManagerProps } from "react-oidc-context";
import type { RuntimeConfig } from "./config/runtime-config";

export function createAuthConfig(config: RuntimeConfig): AuthProviderNoUserManagerProps {
  const sessionStore = new WebStorageStateStore({ store: window.sessionStorage });

  return {
    authority: config.cognitoAuthority,
    client_id: config.cognitoClientId,
    redirect_uri: config.redirectUri,
    post_logout_redirect_uri: config.logoutUri,
    response_type: "code",
    scope: "openid email profile",
    automaticSilentRenew: true,
    loadUserInfo: false,
    monitorSession: false,
    revokeTokensOnSignout: true,
    userStore: sessionStore,
    stateStore: sessionStore,
    onSigninCallback: () => {
      window.history.replaceState({}, document.title, window.location.pathname);
    },
  };
}

export function createCognitoLogoutUrl(config: RuntimeConfig): string {
  const query = new URLSearchParams({
    client_id: config.cognitoClientId,
    logout_uri: config.logoutUri,
  });
  return `${config.cognitoDomain.replace(/\/$/, "")}/logout?${query.toString()}`;
}
