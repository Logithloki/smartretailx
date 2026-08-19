import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "../context/useAuth";
import { useSearchParams } from "react-router-dom";
import { apiFetch, ApiError } from "../api/client";
import type { Order, OrderListResponse } from "../api/types";
import {
  RealtimeUpdate,
  useOrderStatusStream,
} from "../hooks/useOrderStatusStream";
import { Link } from "react-router-dom";
import { formatCurrency } from "../utils/format";

export function MyOrdersPage() {
  const auth = useAuth();
  const token = auth.user?.access_token;
  const [searchParams] = useSearchParams();
  const highlightOrderId = searchParams.get("highlight");

  const [orders, setOrders] = useState<Order[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recentlyUpdated, setRecentlyUpdated] = useState<Set<string>>(
    new Set(),
  );
  const [cancelling, setCancelling] = useState<string | null>(null);

  // Client-side search and status filter
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    apiFetch<OrderListResponse>(token, "/v1/orders", {
      signal: controller.signal,
    })
      .then((data) =>
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

  const applyUpdate = useCallback((update: RealtimeUpdate) => {
    if (update.type === "catalogue.price-refresh") return;
    setOrders((prev) => {
      if (!prev) return prev;
      const idx = prev.findIndex((o) => o.orderId === update.orderId);
      if (idx === -1) return prev;
      const next = [...prev];
      next[idx] = update.type === "order.status-changed"
        ? { ...next[idx], status: update.status }
        : { ...next[idx], fulfilmentStatus: update.fulfilmentStatus };
      return next;
    });
    setRecentlyUpdated((prev) => {
      const next = new Set(prev);
      next.add(update.orderId);
      return next;
    });
    window.setTimeout(() => {
      setRecentlyUpdated((prev) => {
        const next = new Set(prev);
        next.delete(update.orderId);
        return next;
      });
    }, 1500);
  }, []);

  const phase = useOrderStatusStream(token, applyUpdate);

  async function requestCancellation(orderId: string): Promise<void> {
    if (!token) return;
    setCancelling(orderId); setError(null);
    try {
      const updated = await apiFetch<Order>(token, `/v1/orders/${encodeURIComponent(orderId)}/cancel`, { method: "POST" });
      setOrders((previous) => previous?.map((order) => order.orderId === orderId ? updated : order) ?? null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally { setCancelling(null); }
  }

  const wsIndicator = useMemo(() => {
    if (phase === "connected") {
      return (
        <span className="ws-indicator connected">
          <span className="ws-dot"></span> Live Sync
        </span>
      );
    }
    if (phase === "connecting") {
      return <span className="ws-indicator connecting">Connecting...</span>;
    }
    return <span className="ws-indicator dropped">Reconnecting...</span>;
  }, [phase]);

  // Derived stats
  const stats = useMemo(() => {
    if (!orders) return { total: 0, confirmed: 0, pending: 0, rejected: 0, spent: "0.00" };
    let totalCents = 0;
    let confirmed = 0;
    let pending = 0;
    let rejected = 0;
    for (const o of orders) {
      if (o.status === "CONFIRMED") {
        confirmed++;
        totalCents += Math.round(Number(o.totalAmount || 0) * 100);
      } else if (o.status === "PENDING") {
        pending++;
      } else if (o.status === "REJECTED") {
        rejected++;
      }
    }
    return {
      total: orders.length,
      confirmed,
      pending,
      rejected,
      spent: (totalCents / 100).toFixed(2),
    };
  }, [orders]);

  // Filtered orders list
  const filteredOrders = useMemo(() => {
    if (!orders) return [];
    return orders.filter((o) => {
      const matchesSearch =
        search.trim() === "" ||
        o.orderId.toLowerCase().includes(search.toLowerCase()) ||
        o.items.some((i) => i.productId.toLowerCase().includes(search.toLowerCase()));
      const matchesStatus =
        statusFilter === "all" || o.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [orders, search, statusFilter]);

  if (error) {
    return (
      <div className="alert-error">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        Failed to load orders: {error}
      </div>
    );
  }

  if (!orders) {
    return (
      <div className="loading-screen">
        <div className="spinner"></div>
        <p>Loading order history & establishing WebSocket stream...</p>
      </div>
    );
  }

  return (
    <section>
      <div className="page-header">
        <div className="page-title-group">
          <h1>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
            My Orders
            {wsIndicator}
          </h1>
          <p>Real-time order tracking powered by AWS EventBridge Pipes & WebSocket push Lambda.</p>
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <span className="stat-label">Total Orders</span>
          <span className="stat-value">{stats.total}</span>
          <span className="stat-desc">Lifetime orders placed</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Confirmed</span>
          <span className="stat-value" style={{ color: "var(--emerald-600)" }}>{stats.confirmed}</span>
          <span className="stat-desc">Saga execution succeeded</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Pending</span>
          <span className="stat-value" style={{ color: "var(--amber-600)" }}>{stats.pending}</span>
          <span className="stat-desc">Awaiting inventory reserve</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Total Spend</span>
          <span className="stat-value">{formatCurrency(stats.spent)}</span>
          <span className="stat-desc">Confirmed orders subtotal</span>
        </div>
      </div>

      <div className="toolbar">
        <div className="search-input-wrap">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input
            type="text"
            placeholder="Search by Order ID or Product ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="filter-group">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="all">All Statuses ({orders.length})</option>
            <option value="CONFIRMED">CONFIRMED ({stats.confirmed})</option>
            <option value="PENDING">PENDING ({stats.pending})</option>
            <option value="REJECTED">REJECTED ({stats.rejected})</option>
            <option value="CANCEL_PENDING">CANCEL PENDING ({orders.filter((order) => order.status === "CANCEL_PENDING").length})</option>
            <option value="CANCELLED">CANCELLED ({orders.filter((order) => order.status === "CANCELLED").length})</option>
          </select>
        </div>
      </div>

      {filteredOrders.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          </div>
          {orders.length === 0 ? (
            <>
              <h3>No orders yet</h3>
              <p>You haven't placed any orders. Browse the catalogue to start shopping.</p>
              <Link
                to="/products"
                className="btn btn-secondary"
                style={{ marginTop: "1rem" }}
              >
                Browse products
              </Link>
            </>
          ) : (
            <>
              <h3>No orders match your filters</h3>
              <p>Try clearing the search or status filter to see all {orders.length} orders.</p>
              <button
                className="btn btn-secondary"
                style={{ marginTop: "1rem" }}
                onClick={() => {
                  setSearch("");
                  setStatusFilter("all");
                }}
              >
                Reset filters
              </button>
            </>
          )}
        </div>
      ) : (
        <div className="table-container">
          <table className="table">
            <thead>
              <tr>
                <th>Order ID</th>
                <th>Placed Timestamp</th>
                <th>Purchased Items</th>
                <th>Total</th>
                <th>Status & Details</th>
                <th>Delivery tracking</th>
              </tr>
            </thead>
            <tbody>
              {filteredOrders.map((o) => (
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
                    <Link to={`/orders/${encodeURIComponent(o.orderId)}`}>
                      <code>{o.orderId}</code>
                    </Link>
                  </td>
                  <td>{new Date(o.createdAt).toLocaleString()}</td>
                  <td>
                    {o.items
                      .map((i) => `${i.quantity} × ${i.productName || i.productId}`)
                      .join(", ")}
                  </td>
                  <td style={{ fontWeight: 700 }}>{formatCurrency(o.totalAmount)}</td>
                  <td>
                    <span
                      className={`badge ${
                        o.status === "CONFIRMED"
                          ? "badge-confirmed"
                          : o.status === "PENDING" || o.status === "CANCEL_PENDING"
                          ? "badge-pending"
                          : "badge-rejected"
                      }`}
                    >
                      {o.status}
                    </span>
                    {o.statusReason && (
                      <div style={{ fontSize: "0.775rem", color: "var(--text-tertiary)", marginTop: "0.25rem" }}>
                        Reason: {o.statusReason}
                      </div>
                    )}
                    {o.status === "CONFIRMED" && (o.fulfilmentStatus === "NOT_STARTED" || o.fulfilmentStatus === "PACKING") && (
                      <button className="btn btn-secondary btn-sm" style={{ marginTop: "0.5rem" }} disabled={cancelling === o.orderId} onClick={() => void requestCancellation(o.orderId)}>
                        {cancelling === o.orderId ? "Cancelling…" : "Cancel order"}
                      </button>
                    )}
                  </td>
                  <td>
                    <span className="badge badge-pending">
                      {(o.fulfilmentStatus ?? "NOT_STARTED").replaceAll("_", " ")}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

