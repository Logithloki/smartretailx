import { useEffect, useRef, useState } from "react";
import { WEBSOCKET_URL } from "../auth-config";

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
  status: "PENDING" | "CONFIRMED" | "REJECTED";
};

export type WsPhase = "connecting" | "connected" | "dropped";

export function useOrderStatusStream(
  accessToken: string | undefined,
  onUpdate: (update: StatusUpdate) => void,
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
      const url = `${WEBSOCKET_URL}?token=${encodeURIComponent(accessToken!)}`;
      const socket = new WebSocket(url);
      socketRef.current = socket;

      socket.addEventListener("open", () => {
        reconnectDelayRef.current = 1000; // reset backoff on success
        setPhase("connected");
      });

      socket.addEventListener("message", (event) => {
        try {
          const parsed = JSON.parse(event.data) as StatusUpdate;
          if (parsed.type === "order.status-changed") {
            onUpdateRef.current(parsed);
          }
        } catch {
          // Non-JSON server heartbeat / diagnostic. Ignore.
        }
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
