import { useEffect, useRef, useState } from "react";
import { getRuntimeConfig } from "../config/runtime-config";

/*
 * Live-order-status subscriber (backlog item 27, marking Task 4).
 *
 * How it fits into the seam:
 *
 *   Order Service writes DynamoDB status flip
 *      -> DynamoDB Stream MODIFY
 *      -> EventBridge Pipes (native filter: status in
 *         CONFIRMED / REJECTED)
 *      -> EventBridge Bus event `order.status-changed`
 *      -> EventBridge Rule + Target
 *      -> ws-push Lambda scans websocket-connections by userId
 *      -> postToConnection to every live connection
 *      -> THIS HOOK receives it
 *
 * WebSocket handshakes cannot set an Authorization header, so the JWT
 * rides in the query string (?token=...) - the Lambda authoriser reads
 * `route.request.querystring.token` and validates it against Cognito
 * JWKS. Tokens are short-lived (60 min) so we don't need a refresh
 * story inside the hook: react-oidc-context's automaticSilentRenew
 * gives us a fresh token, and when the socket drops we reconnect with
 * whatever is current. Stale-connection cleanup on the server side
 * (GoneException handling in the ws-push Lambda) protects us if we do
 * disappear.
 *
 * Reconnect: exponential backoff capped at 30 s. Cleared on unmount.
 */

export type StatusUpdate = {
  type: "order.status-changed";
  orderId: string;
  status: "PENDING" | "CONFIRMED" | "REJECTED" | "CANCEL_PENDING" | "CANCELLED";
  correlationId?: string | null;
};

export type FulfilmentUpdate = {
  type: "order.fulfilment-status-changed";
  orderId: string;
  fulfilmentStatus: "NOT_STARTED" | "PACKING" | "DISPATCHED" | "OUT_FOR_DELIVERY" | "DELIVERED";
  correlationId?: string | null;
};

export type CataloguePriceRefresh = {
  type: "catalogue.price-refresh";
  productIds: string[];
  revision: number;
};

export type RealtimeUpdate = StatusUpdate | FulfilmentUpdate | CataloguePriceRefresh;

const ORDER_STATUSES = new Set(["PENDING", "CONFIRMED", "REJECTED", "CANCEL_PENDING", "CANCELLED"]);
const FULFILMENT_STATUSES = new Set(["NOT_STARTED", "PACKING", "DISPATCHED", "OUT_FOR_DELIVERY", "DELIVERED"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasOnlyKeys(value: Record<string, unknown>, allowed: Set<string>): boolean {
  return Object.keys(value).every((key) => allowed.has(key));
}

export function parseRealtimeMessage(raw: string): RealtimeUpdate | null {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isRecord(value) || typeof value.type !== "string") return null;

  if (value.type === "catalogue.price-refresh") {
    if (!hasOnlyKeys(value, new Set(["type", "productIds", "revision"]))) return null;
    if (!Array.isArray(value.productIds) || !value.productIds.every((item) => typeof item === "string" && item.length > 0)) {
      return null;
    }
    if (!Number.isSafeInteger(value.revision) || (value.revision as number) < 0) return null;
    return value as CataloguePriceRefresh;
  }

  if (value.type === "order.status-changed") {
    if (!hasOnlyKeys(value, new Set(["type", "orderId", "status", "correlationId"]))) return null;
    if (typeof value.orderId !== "string" || !ORDER_STATUSES.has(String(value.status))) return null;
    if (value.correlationId !== undefined && value.correlationId !== null && typeof value.correlationId !== "string") return null;
    return value as StatusUpdate;
  }

  if (value.type === "order.fulfilment-status-changed") {
    if (!hasOnlyKeys(value, new Set(["type", "orderId", "fulfilmentStatus", "correlationId"]))) return null;
    if (typeof value.orderId !== "string" || !FULFILMENT_STATUSES.has(String(value.fulfilmentStatus))) return null;
    if (value.correlationId !== undefined && value.correlationId !== null && typeof value.correlationId !== "string") return null;
    return value as FulfilmentUpdate;
  }

  return null;
}

export type WsPhase = "connecting" | "connected" | "dropped";

export function useOrderStatusStream(
  accessToken: string | undefined,
  onUpdate: (update: RealtimeUpdate) => void,
): WsPhase {
  const [phase, setPhase] = useState<WsPhase>("connecting");

  // Refs so effect-cleanup can reach the current socket + timers even
  // when React unmounts mid-connect.
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectDelayRef = useRef(1000);
  const reconnectTimerRef = useRef<number | null>(null);
  const cancelledRef = useRef(false);

  // Keep the latest callback in a ref so we don't re-open the socket
  // every time the parent re-renders with a new closure.
  const onUpdateRef = useRef(onUpdate);
  useEffect(() => {
    onUpdateRef.current = onUpdate;
  }, [onUpdate]);

  useEffect(() => {
    if (!accessToken) return;
    cancelledRef.current = false;

    function connect() {
      if (cancelledRef.current) return;
      setPhase("connecting");
      const url = `${getRuntimeConfig().websocketUrl}?token=${encodeURIComponent(accessToken!)}`;
      const socket = new WebSocket(url);
      socketRef.current = socket;

      socket.addEventListener("open", () => {
        reconnectDelayRef.current = 1000; // reset backoff on success
        setPhase("connected");
      });

      socket.addEventListener("message", (event) => {
        const parsed = typeof event.data === "string" ? parseRealtimeMessage(event.data) : null;
        if (parsed) onUpdateRef.current(parsed);
      });

      socket.addEventListener("close", () => {
        socketRef.current = null;
        if (cancelledRef.current) return;
        setPhase("dropped");
        // Exponential backoff, capped at 30 s so a viva demo does not
        // silently sit dead for a minute after a network blip.
        const delay = Math.min(reconnectDelayRef.current, 30_000);
        reconnectDelayRef.current *= 2;
        reconnectTimerRef.current = window.setTimeout(connect, delay);
      });

      socket.addEventListener("error", () => {
        // Errors are followed by a close event; nothing extra to do.
      });
    }

    connect();

    return () => {
      cancelledRef.current = true;
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
      }
      socketRef.current?.close();
    };
  }, [accessToken]);

  return phase;
}
