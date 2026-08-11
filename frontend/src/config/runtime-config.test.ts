import { describe, expect, it } from "vitest";
import { parseRuntimeConfig } from "./runtime-config";

const validConfig = {
  apiBaseUrl: "",
  websocketUrl: "wss://ws.example.com/prod",
  cognitoAuthority:
    "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_example",
  cognitoDomain: "https://smartretailx.auth.eu-west-1.amazoncognito.com",
  cognitoClientId: "client-id",
  redirectUri: "https://app.example.com/callback",
  logoutUri: "https://app.example.com/",
  environment: "production",
  releaseId: "release-2026-08-09",
};

describe("parseRuntimeConfig", () => {
  it("accepts same-origin API routing and secure hosted endpoints", () => {
    expect(parseRuntimeConfig(validConfig)).toEqual(validConfig);
  });

  it("rejects a missing release identifier", () => {
    expect(() =>
      parseRuntimeConfig({ ...validConfig, releaseId: "" }),
    ).toThrow("releaseId");
  });

  it("rejects an API base URL containing the legacy /api prefix", () => {
    expect(() =>
      parseRuntimeConfig({ ...validConfig, apiBaseUrl: "https://app.example.com/api" }),
    ).toThrow("apiBaseUrl");
  });

  it("permits ws only for explicit local development", () => {
    expect(() =>
      parseRuntimeConfig({ ...validConfig, websocketUrl: "ws://ws.example.com/prod" }),
    ).toThrow("websocketUrl");

    expect(
      parseRuntimeConfig({
        ...validConfig,
        environment: "local",
        websocketUrl: "ws://localhost:9001",
        redirectUri: "http://localhost:5173/callback",
        logoutUri: "http://localhost:5173/",
      }).environment,
    ).toBe("local");
  });
});
