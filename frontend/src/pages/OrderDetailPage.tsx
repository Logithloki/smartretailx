import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../context/useAuth";
import { apiFetch, ApiError } from "../api/client";
import type { Order } from "../api/types";
import {
  RealtimeUpdate,
  useOrderStatusStream,
} from "../hooks/useOrderStatusStream";
import { formatCurrency } from "../utils/format";

const STATUS_BADGE: Record<string, string> = {
  CONFIRMED: "badge-confirmed",
  PENDING: "badge-pending",
  CANCEL_PENDING: "badge-pending",
  REJECTED: "badge-rejected",
  CANCELLED: "badge-rejected",
};

const FULFILMENT_STEPS = [
  "NOT_STARTED",
  "PACKING",
  "DISPATCHED",
  "OUT_FOR_DELIVERY",
  "DELIVERED",
] as const;

export function OrderDetailPage() {
  const { orderId } = useParams<{ orderId: string }>();
  const auth = useAuth();
  const token = auth.user?.access_token;

  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  useEffect(() => {
    if (!token || !orderId) return;
    const controller = new AbortController();
    apiFetch<Order>(token, `/v1/orders/${encodeURIComponent(orderId)}`, {
      signal: controller.signal,
    })
      .then((data) => setOrder(data))
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof ApiError ? err.message : String(err));
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [token, orderId]);

  const applyUpdate = useCallback(
    (update: RealtimeUpdate) => {
      if (update.type === "catalogue.price-refresh") return;
      if (update.orderId !== orderId) return;
      setOrder((prev) => {
        if (!prev) return prev;
        if (update.type === "order.status-changed") {
          return { ...prev, status: update.status };
        }
        return { ...prev, fulfilmentStatus: update.fulfilmentStatus };
      });
      setFlash(true);
      window.setTimeout(() => setFlash(false), 1500);
    },
    [orderId],
  );

  const phase = useOrderStatusStream(token, applyUpdate);

  async function requestCancellation(): Promise<void> {
    if (!token || !orderId) return;
    setCancelling(true);
    setError(null);
    try {
      const updated = await apiFetch<Order>(
        token,
        `/v1/orders/${encodeURIComponent(orderId)}/cancel`,
        { method: "POST" },
      );
      setOrder(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setCancelling(false);
    }
  }

  const wsIndicator = useMemo(() => {
    if (phase === "connected")
      return (
        <span className="ws-indicator connected">
          <span className="ws-dot"></span> Live
        </span>
      );
    if (phase === "connecting")
      return <span className="ws-indicator connecting">Connecting...</span>;
    return <span className="ws-indicator dropped">Reconnecting...</span>;
  }, [phase]);

  const fulfilmentIndex = order
    ? FULFILMENT_STEPS.indexOf(
        order.fulfilmentStatus as (typeof FULFILMENT_STEPS)[number],
      )
    : -1;

  const canCancel =
    order?.status === "CONFIRMED" &&
    (order.fulfilmentStatus === "NOT_STARTED" ||
      order.fulfilmentStatus === "PACKING");

  if (loading) {
    return (
      <div className="loading-screen">
        <div className="spinner"></div>
        <p>Loading order details...</p>
      </div>
    );
  }

  if (error && !order) {
    return (
      <section>
        <div className="alert-error" role="alert">
          {error}
        </div>
        <Link to="/orders" className="btn btn-secondary" style={{ marginTop: "1rem" }}>
          Back to orders
        </Link>
      </section>
    );
  }

  if (!order) {
    return (
      <section className="empty-state">
        <h1>Order not found</h1>
        <Link to="/orders" className="btn btn-secondary">
          Back to orders
        </Link>
      </section>
    );
  }

  return (
    <section>
      <div className="page-header">
        <div className="page-title-group">
          <h1>
            Order <code>{order.orderId}</code>
            {wsIndicator}
          </h1>
          <p>
            Placed {new Date(order.createdAt).toLocaleString()} &middot;
            Last updated {new Date(order.updatedAt).toLocaleString()}
          </p>
        </div>
        <Link to="/orders" className="btn btn-secondary">
          All orders
        </Link>
      </div>

      {error && <div className="alert-error" role="alert">{error}</div>}

      <div className="stats-grid">
        <div className={`stat-card${flash ? " updated" : ""}`}>
          <span className="stat-label">Status</span>
          <span className="stat-value">
            <span className={`badge ${STATUS_BADGE[order.status] ?? "badge-pending"}`}>
              {order.status}
            </span>
          </span>
          {order.statusReason && (
            <span className="stat-desc">{order.statusReason}</span>
          )}
        </div>
        <div className={`stat-card${flash ? " updated" : ""}`}>
          <span className="stat-label">Fulfilment</span>
          <span className="stat-value">
            <span className="badge badge-pending">
              {(order.fulfilmentStatus ?? "NOT_STARTED").replaceAll("_", " ")}
            </span>
          </span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Total</span>
          <span className="stat-value">{formatCurrency(order.totalAmount)}</span>
          <span className="stat-desc">Authoritative server total</span>
        </div>
      </div>

      {order.status === "CONFIRMED" && (
        <div className="form-card" style={{ marginTop: "1.5rem" }}>
          <h2 style={{ fontSize: "0.9rem", fontWeight: 600, marginBottom: "1rem" }}>
            Fulfilment progress
          </h2>
          <div className="fulfilment-tracker" role="progressbar" aria-valuenow={fulfilmentIndex + 1} aria-valuemin={1} aria-valuemax={FULFILMENT_STEPS.length} aria-label="Fulfilment progress">
            {FULFILMENT_STEPS.map((step, i) => (
              <div
                key={step}
                className={`fulfilment-step${i <= fulfilmentIndex ? " complete" : ""}${i === fulfilmentIndex ? " current" : ""}`}
              >
                <div className="fulfilment-dot" />
                <span className="fulfilment-label">
                  {step.replaceAll("_", " ")}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="form-card" style={{ marginTop: "1.5rem" }}>
        <h2 style={{ fontSize: "0.9rem", fontWeight: 600, marginBottom: "1rem" }}>
          Line items
        </h2>
        <div className="table-container">
          <table className="table">
            <thead>
              <tr>
                <th>Product</th>
                <th>Qty</th>
                <th>Unit price</th>
                <th>Effective</th>
                <th>Discount</th>
                <th>Line total</th>
              </tr>
            </thead>
            <tbody>
              {order.items.map((item) => (
                <tr key={item.productId}>
                  <td>{item.productName || item.productId}</td>
                  <td>{item.quantity}</td>
                  <td>{formatCurrency(item.baseUnitPrice)}</td>
                  <td>{formatCurrency(item.effectiveUnitPrice)}</td>
                  <td>{formatCurrency(item.lineDiscount)}</td>
                  <td style={{ fontWeight: 700 }}>
                    {formatCurrency(item.lineTotal)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="order-summary-card" style={{ marginTop: "1.5rem" }}>
        <div className="summary-row">
          <span>Subtotal</span>
          <strong>{formatCurrency(order.subtotal)}</strong>
        </div>
        <div className="summary-row">
          <span>Discount</span>
          <strong>&minus;{formatCurrency(order.discountTotal)}</strong>
        </div>
        <div className="summary-row total">
          <span>Order total</span>
          <strong>{formatCurrency(order.totalAmount)}</strong>
        </div>
        {canCancel && (
          <button
            className="btn btn-secondary"
            style={{ marginTop: "1rem" }}
            disabled={cancelling}
            onClick={() => void requestCancellation()}
          >
            {cancelling ? "Cancelling..." : "Cancel order"}
          </button>
        )}
      </div>
    </section>
  );
}
