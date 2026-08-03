import { API_BASE_URL } from "../auth-config";

/*
 * Thin fetch wrapper that centralises three concerns for the whole SPA:
 *
 *   1. Auth: every request gets `Authorization: Bearer <access_token>`.
 *      Access tokens are what API Gateway's JWT authoriser validates
 *      (aud = app client id). ID tokens would be rejected.
 *   2. Idempotency: mutation calls that opt in get a UUID `Idempotency-
 *      Key` header. The backend uses per-user + payload-fingerprint
 *      claim (see the Order Service's create_order handler). Re-sending
 *      the same UUID with the same body -> the cached first response;
 *      same UUID with a different body -> 422.
 *   3. Errors: non-2xx becomes a typed ApiError so pages can surface
 *      the message without repeating `if (!res.ok)` in every hook.
 *
 * Deliberately NOT using axios or a query library like TanStack Query:
 * this app makes ~8 endpoint calls total, and every extra dep is a
 * larger bundle over the CloudFront wire.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    super(`HTTP ${status}: ${body}`);
    this.status = status;
    this.body = body;
    this.name = "ApiError";
  }
}

export interface ApiOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  // If true, generate a fresh UUID and send it as Idempotency-Key. Only
  // used on POST /v1/orders today; other mutations may adopt it later.
  idempotent?: boolean;
  signal?: AbortSignal;
}

function newIdempotencyKey(): string {
  // crypto.randomUUID is on every modern browser AND on Node 20 (the
  // GitHub Actions build environment). Safer than a Math.random ID.
  return crypto.randomUUID();
}

export async function apiFetch<T>(
  accessToken: string,
  path: string,
  opts: ApiOptions = {},
): Promise<T> {
  if (!path.startsWith("/")) {
    throw new Error(`apiFetch path must start with '/' (got '${path}')`);
  }

  const headers: Record<string, string> = {
    Authorization: `Bearer ${accessToken}`,
  };

  let body: BodyInit | undefined;
  if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }

  if (opts.idempotent) {
    headers["Idempotency-Key"] = newIdempotencyKey();
  }

  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: opts.method ?? (body ? "POST" : "GET"),
    headers,
    body,
    signal: opts.signal,
  });

  if (!res.ok) {
    // Backend responses use FastAPI's default {"detail": "..."} shape;
    // fall back to raw text if it isn't JSON.
    const text = await res.text();
    throw new ApiError(res.status, text);
  }

  // A 204 has no body; every other 2xx does in this API.
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
