export const environments = [
  "local",
  "sandbox",
  "development",
  "test",
  "staging",
  "production",
  "baseline",
] as const;

export type EnvironmentName = (typeof environments)[number];

export interface RuntimeConfig {
  apiBaseUrl: string;
  websocketUrl: string;
  cognitoAuthority: string;
  cognitoDomain: string;
  cognitoClientId: string;
  redirectUri: string;
  logoutUri: string;
  environment: EnvironmentName;
  releaseId: string;
}

let activeConfig: RuntimeConfig | undefined;

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("runtime config must be a JSON object");
  }
  return value as Record<string, unknown>;
}

function requiredString(
  source: Record<string, unknown>,
  name: keyof RuntimeConfig,
): string {
  const value = source[name];
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`runtime config ${name} must be a non-empty string`);
  }
  return value.trim();
}

function url(
  source: Record<string, unknown>,
  name: "cognitoAuthority" | "cognitoDomain" | "redirectUri" | "logoutUri",
  allowLocalHttp: boolean,
): string {
  const value = requiredString(source, name);
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`runtime config ${name} must be an absolute URL`);
  }

  const localHttp =
    allowLocalHttp &&
    parsed.protocol === "http:" &&
    ["localhost", "127.0.0.1"].includes(parsed.hostname);
  if (parsed.protocol !== "https:" && !localHttp) {
    throw new Error(`runtime config ${name} must use HTTPS`);
  }
  return value;
}

export function parseRuntimeConfig(input: unknown): RuntimeConfig {
  const source = record(input);
  const environmentValue = requiredString(source, "environment");
  if (!environments.includes(environmentValue as EnvironmentName)) {
    throw new Error(`runtime config environment is unsupported: ${environmentValue}`);
  }
  const environment = environmentValue as EnvironmentName;
  const isLocal = environment === "local";

  const apiValue = source.apiBaseUrl;
  if (typeof apiValue !== "string") {
    throw new Error("runtime config apiBaseUrl must be a string");
  }
  const apiBaseUrl = apiValue.replace(/\/$/, "");
  if (apiBaseUrl) {
    let parsed: URL;
    try {
      parsed = new URL(apiBaseUrl);
    } catch {
      throw new Error("runtime config apiBaseUrl must be empty or an absolute URL");
    }
    if (parsed.pathname !== "/" && parsed.pathname !== "") {
      throw new Error("runtime config apiBaseUrl must be an origin without /api or /v1");
    }
    if (parsed.protocol !== "https:" && !(isLocal && parsed.protocol === "http:")) {
      throw new Error("runtime config apiBaseUrl must use HTTPS outside local development");
    }
  }

  const websocketUrl = requiredString(source, "websocketUrl").replace(/\/$/, "");
  let parsedWebsocket: URL;
  try {
    parsedWebsocket = new URL(websocketUrl);
  } catch {
    throw new Error("runtime config websocketUrl must be an absolute URL");
  }
  if (
    parsedWebsocket.protocol !== "wss:" &&
    !(isLocal && parsedWebsocket.protocol === "ws:" &&
      ["localhost", "127.0.0.1"].includes(parsedWebsocket.hostname))
  ) {
    throw new Error("runtime config websocketUrl must use WSS outside local development");
  }

  return {
    apiBaseUrl,
    websocketUrl,
    cognitoAuthority: url(source, "cognitoAuthority", isLocal),
    cognitoDomain: url(source, "cognitoDomain", isLocal),
    cognitoClientId: requiredString(source, "cognitoClientId"),
    redirectUri: url(source, "redirectUri", isLocal),
    logoutUri: url(source, "logoutUri", isLocal),
    environment,
    releaseId: requiredString(source, "releaseId"),
  };
}

export async function loadRuntimeConfig(
  fetchConfig: typeof fetch = fetch,
): Promise<RuntimeConfig> {
  const response = await fetchConfig("/config.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`unable to load runtime config: HTTP ${response.status}`);
  }
  activeConfig = parseRuntimeConfig(await response.json());
  return activeConfig;
}

export function setRuntimeConfig(config: RuntimeConfig): void {
  activeConfig = config;
}

export function getRuntimeConfig(): RuntimeConfig {
  if (!activeConfig) {
    throw new Error("runtime config has not been loaded");
  }
  return activeConfig;
}
