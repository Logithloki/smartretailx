import { describe, expect, it } from "vitest";
import type { RuntimeConfig } from "./config/runtime-config";
import { createAuthConfig, createCognitoLogoutUrl } from "./auth-config";

const config: RuntimeConfig = {
  apiBaseUrl: "",
  websocketUrl: "wss://ws.example.com/prod",
  cognitoAuthority:
    "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_example",
  cognitoDomain: "https://smartretailx.auth.eu-west-1.amazoncognito.com",
  cognitoClientId: "client-id",
  redirectUri: "https://app.example.com/callback",
  logoutUri: "https://app.example.com/",
  environment: "production",
  releaseId: "release-1",
};

describe("createAuthConfig", () => {
  it("uses authorization code, PKCE-capable library state and session storage", () => {
    const auth = createAuthConfig(config);

    expect(auth.authority).toBe(config.cognitoAuthority);
    expect(auth.client_id).toBe(config.cognitoClientId);
    expect(auth.redirect_uri).toBe(config.redirectUri);
    expect(auth.response_type).toBe("code");
    expect(auth.automaticSilentRenew).toBe(true);
    expect(auth.userStore).toBeDefined();
    expect(auth.stateStore).toBeDefined();
  });
});

describe("createCognitoLogoutUrl", () => {
  it("returns Cognito managed-login logout with an allow-listed redirect", () => {
    expect(createCognitoLogoutUrl(config)).toBe(
      "https://smartretailx.auth.eu-west-1.amazoncognito.com/logout" +
        "?client_id=client-id&logout_uri=https%3A%2F%2Fapp.example.com%2F",
    );
  });
});
