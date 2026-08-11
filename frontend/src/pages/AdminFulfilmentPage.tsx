import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "../api/client";
import type { FulfilmentStatus, Order, OrderListResponse } from "../api/types";
import { useAuth } from "../context/useAuth";

const nextStatus: Partial<Record<FulfilmentStatus, FulfilmentStatus>> = {
  NOT_STARTED: "PACKING", PACKING: "DISPATCHED", DISPATCHED: "OUT_FOR_DELIVERY", OUT_FOR_DELIVERY: "DELIVERED",
};

export function AdminFulfilmentPage() {
  const auth = useAuth(); const token = auth.user?.access_token;
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const reload = () => { if (token) apiFetch<OrderListResponse>(token, "/v1/orders/operations").then((data) => setOrders(data.orders)).catch((err: unknown) => setError(err instanceof ApiError ? err.message : String(err))); };
  useEffect(reload, [token]);
  async function progress(order: Order) {
    const target = nextStatus[order.fulfilmentStatus]; if (!token || !target) return;
    setBusy(order.orderId); setError(null);
    try { await apiFetch<Order>(token, `/v1/orders/${encodeURIComponent(order.orderId)}/fulfilment`, { method: "PATCH", body: { status: target } }); reload(); }
    catch (err) { setError(err instanceof ApiError ? err.message : String(err)); } finally { setBusy(null); }
  }
  if (!orders) return <div className="loading-screen"><p>Loading fulfilment queue…</p></div>;
  return <section><div className="page-header"><div className="page-title-group"><h1>Operations: fulfilment</h1><p>Confirmed orders progress through a conditional, event-backed delivery workflow.</p></div></div>{error && <div className="alert-error">{error}</div>}<div className="table-container"><table className="table"><thead><tr><th>Order</th><th>Customer</th><th>Items</th><th>Order status</th><th>Delivery status</th><th /></tr></thead><tbody>{orders.map((order) => { const target = nextStatus[order.fulfilmentStatus]; return <tr key={order.orderId}><td><code>{order.orderId}</code></td><td>{order.userId}</td><td>{order.items.map((item) => `${item.quantity} × ${item.productName}`).join(", ")}</td><td>{order.status}</td><td>{order.fulfilmentStatus}</td><td>{order.status === "CONFIRMED" && target ? <button className="btn btn-sm" disabled={busy === order.orderId} onClick={() => void progress(order)}>{busy === order.orderId ? "Updating…" : `Mark ${target}`}</button> : "—"}</td></tr>; })}</tbody></table></div></section>;
}
