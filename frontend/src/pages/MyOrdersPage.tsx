import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "react-oidc-context";
import { useSearchParams } from "react-router-dom";
import { apiFetch, ApiError } from "../api/client";
import type { Order, OrderListResponse } from "../api/types";
import {
  StatusUpdate,
  useOrderStatusStream,
} from "../hooks/useOrderStatusStream";

/*
 * My Orders + live status (backlog item 27, marking brief Task 4).
 *
 * This is the SPA half of the real-time story. Backend half is:
 *   DynamoDB stream -> Pipes -> EventBridge -> ws-push Lambda ->
 *   postToConnection to every websocket-connections row for this
 *   userId (see infra/pipes.tf + infra/websocket.tf +
 *   services/ws-push-lambda/handler.py).
 *
 * The page opens exactly one WebSocket, keeps it open while mounted,
 * and merges any `order.status-changed` message into local state. A
 * highlight flash draws the eye to the updated row so the viva
 * demonstrator does not have to point at the screen.
 *
 * A newly-placed order is passed in via ?highlight=<orderId> from the
 * PlaceOrderPage redirect; that row starts flashing immediately so the
 * PENDING -> CONFIRMED transition is unmissable.
 */
export function MyOrdersPage() {
  const auth = useAuth();
  const token = auth.user?.access_token;
  const [searchParams] = useSearchParams();
  const highlightOrderId = searchParams.get("highlight");

  const [orders, setOrders] = useState<Order[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Order ids that got a live update recently — used to CSS-flash the
  // corresponding row. Cleared after the animation completes.
  const [recentlyUpdated, setRecentlyUpdated] = useState<Set<string>>(
    new Set(),
  );

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    apiFetch<OrderListResponse>(token, "/v1/orders", {
      signal: controller.signal,
    })
      .then((data) =>
        // Newest first - server also does this but be defensive.
        setOrders(
          [...data.orders].sort((a, b) =>
            b.createdAt.localeCompare(a.createdAt),
          ),
        ),
      )
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof ApiError ? err.message : String(err));
      });
    return () => controller.abort();
  }, [token]);

  const applyUpdate = useCallback((update: StatusUpdate) => {
    setOrders((prev) => {
      if (!prev) return prev;
      const idx = prev.findIndex((o) => o.orderId === update.orderId);
      if (idx === -1) return prev;
      const next = [...prev];
      next[idx] = { ...next[idx], status: update.status };
      return next;
    });
    setRecentlyUpdated((prev) => {
      const next = new Set(prev);
      next.add(update.orderId);
      return next;
    });
    // Clear the flash animation flag after the CSS animation runs.
    // Keeping it as state means the row does not endlessly animate.
    window.setTimeout(() => {
      setRecentlyUpdated((prev) => {
        const next = new Set(prev);
        next.delete(update.orderId);
        return next;
      });
    }, 1500);
  }, []);

  const phase = useOrderStatusStream(token, applyUpdate);

  const wsIndicator = useMemo(() => {
    if (phase === "connected") return "● live";
    if (phase === "connecting") return "○ connecting…";
    return "● reconnecting…";
  }, [phase]);

  if (error) return <p className="error">Failed to load orders: {error}</p>;
  if (!orders) return <p>Loading orders...</p>;

  return (
    <section>
      <h1>
        My orders <span className={`ws-indicator ${phase}`}>{wsIndicator}</span>
      </h1>

      {orders.length === 0 ? (
        <p>You haven't placed any orders yet.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Order ID</th>
              <th>Placed</th>
              <th>Items</th>
              <th>Total</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((o) => (
              <tr
                key={o.orderId}
                className={[
                  o.orderId === highlightOrderId ? "highlight" : "",
                  recentlyUpdated.has(o.orderId) ? "updated" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                <td>
                  <code>{o.orderId}</code>
                </td>
                <td>{new Date(o.createdAt).toLocaleString()}</td>
                <td>
                  {o.items
                    .map((i) => `${i.quantity} × ${i.productId}`)
                    .join(", ")}
                </td>
                <td>£{o.totalAmount}</td>
                <td>
                  <span className={`status status-${o.status}`}>
                    {o.status}
                  </span>
                  {o.statusReason && (
                    <p className="meta">{o.statusReason}</p>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
