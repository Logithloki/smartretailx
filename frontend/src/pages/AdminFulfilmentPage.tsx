import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, ApiError } from "../api/client";
import type { FulfilmentStatus, Order, OrderListResponse, OrderSummaryResponse } from "../api/types";
import { useAuth } from "../context/useAuth";
import { RealtimeUpdate, useOrderStatusStream } from "../hooks/useOrderStatusStream";
import { formatCurrency } from "../utils/format";

const FULFILMENT_STEPS: FulfilmentStatus[] = [
  "NOT_STARTED", "PACKING", "DISPATCHED", "OUT_FOR_DELIVERY", "DELIVERED",
];

const NEXT_STATUS: Partial<Record<FulfilmentStatus, FulfilmentStatus>> = {
  NOT_STARTED: "PACKING",
  PACKING: "DISPATCHED",
  DISPATCHED: "OUT_FOR_DELIVERY",
  OUT_FOR_DELIVERY: "DELIVERED",
};

const ACTION_LABELS: Partial<Record<FulfilmentStatus, string>> = {
  PACKING: "Start packing",
  DISPATCHED: "Mark dispatched",
  OUT_FOR_DELIVERY: "Out for delivery",
  DELIVERED: "Mark delivered",
};

function fulfilmentBadgeClass(status: FulfilmentStatus): string {
  switch (status) {
    case "DELIVERED": return "badge-confirmed";
    case "NOT_STARTED": return "badge-pending";
    default: return "badge-fulfilment-active";
  }
}

function orderStatusBadgeClass(status: string): string {
  switch (status) {
    case "CONFIRMED": return "badge-confirmed";
    case "PENDING":
    case "CANCEL_PENDING": return "badge-pending";
    default: return "badge-rejected";
  }
}

type FilterKey = "all" | "needs_action" | "in_progress" | "delivered" | "cancelled";

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "All orders" },
  { key: "needs_action", label: "Needs action" },
  { key: "in_progress", label: "In progress" },
  { key: "delivered", label: "Delivered" },
  { key: "cancelled", label: "Cancelled" },
];

function matchesFilter(order: Order, filter: FilterKey): boolean {
  switch (filter) {
    case "needs_action":
      return order.status === "CONFIRMED" && order.fulfilmentStatus === "NOT_STARTED";
    case "in_progress":
      return order.status === "CONFIRMED" &&
        (order.fulfilmentStatus === "PACKING" || order.fulfilmentStatus === "DISPATCHED" || order.fulfilmentStatus === "OUT_FOR_DELIVERY");
    case "delivered":
      return order.fulfilmentStatus === "DELIVERED";
    case "cancelled":
      return order.status === "CANCELLED" || order.status === "REJECTED";
    default:
      return true;
  }
}

function filterCount(orders: Order[], filter: FilterKey): number {
  return orders.filter((o) => matchesFilter(o, filter)).length;
}

function humanFulfilment(status: FulfilmentStatus): string {
  return status.replaceAll("_", " ");
}

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export function AdminFulfilmentPage() {
  const auth = useAuth();
  const token = auth.user?.access_token;

  const [orders, setOrders] = useState<Order[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);
  const [recentlyUpdated, setRecentlyUpdated] = useState<Set<string>>(new Set());
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const reload = useCallback(() => {
    if (!token) return;
    apiFetch<OrderListResponse>(token, "/v1/orders/operations")
      .then((data) => {
        setOrders(data.orders.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)));
        setError(null);
      })
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(reload, [reload]);

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
    setRecentlyUpdated((prev) => new Set(prev).add(update.orderId));
    window.setTimeout(() => {
      setRecentlyUpdated((prev) => {
        const next = new Set(prev);
        next.delete(update.orderId);
        return next;
      });
    }, 2000);
  }, []);

  const wsPhase = useOrderStatusStream(token, applyUpdate);

  async function progressOrder(order: Order): Promise<void> {
    const target = NEXT_STATUS[order.fulfilmentStatus];
    if (!token || !target) return;
    setBusy(order.orderId);
    setError(null);
    setConflict(null);
    try {
      const updated = await apiFetch<Order>(
        token,
        `/v1/orders/${encodeURIComponent(order.orderId)}/fulfilment`,
        { method: "PATCH", body: { status: target } },
      );
      setOrders((prev) =>
        prev?.map((o) => (o.orderId === updated.orderId ? updated : o)) ?? null,
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setConflict(order.orderId);
        reload();
      } else {
        setError(err instanceof ApiError ? err.message : String(err));
      }
    } finally {
      setBusy(null);
    }
  }

  async function downloadSummary(orderId: string): Promise<void> {
    if (!token) return;
    setDownloadingId(orderId);
    setError(null);
    try {
      const result = await apiFetch<OrderSummaryResponse>(
        token,
        `/v1/orders/${encodeURIComponent(orderId)}/summary`,
      );
      window.open(result.url, "_blank", "noopener");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setDownloadingId(null);
    }
  }

  const stats = useMemo(() => {
    if (!orders) return { needsAction: 0, inProgress: 0, delivered: 0, cancelled: 0 };
    return {
      needsAction: filterCount(orders, "needs_action"),
      inProgress: filterCount(orders, "in_progress"),
      delivered: filterCount(orders, "delivered"),
      cancelled: filterCount(orders, "cancelled"),
    };
  }, [orders]);

  const filtered = useMemo(() => {
    if (!orders) return [];
    return orders.filter((o) => {
      if (!matchesFilter(o, filter)) return false;
      if (search.trim()) {
        const q = search.toLowerCase();
        return o.orderId.toLowerCase().includes(q) ||
          o.items.some((i) => i.productName.toLowerCase().includes(q));
      }
      return true;
    });
  }, [orders, filter, search]);

  const selected = useMemo(
    () => (selectedId ? orders?.find((o) => o.orderId === selectedId) ?? null : null),
    [orders, selectedId],
  );

  if (loading) {
    return (
      <div className="loading-screen">
        <div className="spinner"></div>
        <p>Loading fulfilment queue...</p>
      </div>
    );
  }

  if (error && !orders) {
    return (
      <section>
        <div className="alert-error" role="alert">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          {error}
        </div>
        <button className="btn btn-secondary" style={{ marginTop: "1rem" }} onClick={reload}>Retry</button>
      </section>
    );
  }

  return (
    <section>
      <div className="page-header">
        <div className="page-title-group">
          <h1>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="1" y="3" width="15" height="13"/><polygon points="16 8 20 8 23 11 23 16 16 16 16 8"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>
            Admin: Fulfilment
            {wsPhase === "connected" && (
              <span className="ws-indicator connected"><span className="ws-dot"></span> Live</span>
            )}
          </h1>
          <p>Progress confirmed orders through the delivery workflow. State transitions emit domain events that update customer tracking in real time.</p>
        </div>
        <button className="btn btn-secondary" onClick={reload} aria-label="Refresh order queue">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
          Refresh
        </button>
      </div>

      {error && (
        <div className="alert-error" role="alert" style={{ marginBottom: "1rem" }}>
          {error}
        </div>
      )}

      {conflict && (
        <div className="alert-warning" role="alert" style={{ marginBottom: "1rem" }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          Order was updated by another session. The queue has been refreshed with the latest state.
          <button className="btn btn-secondary btn-sm" style={{ marginLeft: "auto" }} onClick={() => setConflict(null)}>Dismiss</button>
        </div>
      )}

      <div className="stats-grid">
        <div className="stat-card" role="status">
          <span className="stat-label">Needs action</span>
          <span className="stat-value" style={{ color: "var(--amber-600)" }}>{stats.needsAction}</span>
          <span className="stat-desc">Confirmed, not yet packing</span>
        </div>
        <div className="stat-card" role="status">
          <span className="stat-label">In progress</span>
          <span className="stat-value" style={{ color: "var(--indigo-600)" }}>{stats.inProgress}</span>
          <span className="stat-desc">Packing / dispatched / out for delivery</span>
        </div>
        <div className="stat-card" role="status">
          <span className="stat-label">Delivered</span>
          <span className="stat-value" style={{ color: "var(--emerald-600)" }}>{stats.delivered}</span>
          <span className="stat-desc">Completed deliveries</span>
        </div>
        <div className="stat-card" role="status">
          <span className="stat-label">Cancelled / Rejected</span>
          <span className="stat-value" style={{ color: "var(--rose-600)" }}>{stats.cancelled}</span>
          <span className="stat-desc">Saga compensation or customer cancellation</span>
        </div>
      </div>

      <div className="toolbar">
        <div className="search-input-wrap">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input
            type="text"
            placeholder="Search by order ID or product name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search orders"
          />
        </div>
        <div className="filter-group" role="group" aria-label="Filter orders">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              className={`btn btn-sm ${filter === f.key ? "" : "btn-secondary"}`}
              onClick={() => setFilter(f.key)}
              aria-pressed={filter === f.key}
            >
              {f.label} ({orders ? filterCount(orders, f.key) : 0})
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="1" y="3" width="15" height="13"/><polygon points="16 8 20 8 23 11 23 16 16 16 16 8"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>
          </div>
          {orders && orders.length === 0 ? (
            <>
              <h3>No orders in the system</h3>
              <p>The fulfilment queue is empty. Orders will appear here once customers place them.</p>
            </>
          ) : (
            <>
              <h3>No orders match the current filter</h3>
              <p>Try a different filter or clear the search.</p>
              <button className="btn btn-secondary" style={{ marginTop: "1rem" }} onClick={() => { setFilter("all"); setSearch(""); }}>
                Reset filters
              </button>
            </>
          )}
        </div>
      ) : (
        <div className="table-container">
          <table className="table" aria-label="Fulfilment queue">
            <thead>
              <tr>
                <th scope="col">Order</th>
                <th scope="col">Created</th>
                <th scope="col">Items</th>
                <th scope="col">Total</th>
                <th scope="col">Order status</th>
                <th scope="col">Fulfilment</th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((order) => {
                const target = NEXT_STATUS[order.fulfilmentStatus];
                const canProgress = order.status === "CONFIRMED" && target;
                const isBusy = busy === order.orderId;
                return (
                  <tr
                    key={order.orderId}
                    className={recentlyUpdated.has(order.orderId) ? "updated" : ""}
                    style={{ cursor: "pointer" }}
                    onClick={() => setSelectedId(order.orderId === selectedId ? null : order.orderId)}
                    aria-selected={selectedId === order.orderId}
                  >
                    <td><code>{order.orderId}</code></td>
                    <td>{formatTimestamp(order.createdAt)}</td>
                    <td>
                      {order.items.length} item{order.items.length !== 1 ? "s" : ""}
                    </td>
                    <td style={{ fontWeight: 700 }}>{formatCurrency(order.totalAmount)}</td>
                    <td>
                      <span className={`badge ${orderStatusBadgeClass(order.status)}`}>
                        {order.status}
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${fulfilmentBadgeClass(order.fulfilmentStatus)}`}>
                        {humanFulfilment(order.fulfilmentStatus)}
                      </span>
                    </td>
                    <td>
                      {canProgress ? (
                        <button
                          className="btn btn-sm"
                          disabled={isBusy}
                          onClick={(e) => { e.stopPropagation(); void progressOrder(order); }}
                          aria-label={`${ACTION_LABELS[target!]} for order ${order.orderId}`}
                        >
                          {isBusy ? "Updating..." : ACTION_LABELS[target!]}
                        </button>
                      ) : (
                        <span style={{ color: "var(--text-muted)" }}>&mdash;</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <div
          className="fulfilment-detail-overlay"
          onClick={() => setSelectedId(null)}
          role="dialog"
          aria-modal="true"
          aria-label={`Order detail for ${selected.orderId}`}
        >
          <div className="fulfilment-detail-drawer" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-header">
              <h2>Order <code>{selected.orderId}</code></h2>
              <button className="btn btn-secondary btn-sm" onClick={() => setSelectedId(null)} aria-label="Close detail panel">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>

            <div className="drawer-body">
              <div className="stats-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
                <div className="stat-card">
                  <span className="stat-label">Order status</span>
                  <span className={`badge ${orderStatusBadgeClass(selected.status)}`}>{selected.status}</span>
                  {selected.statusReason && <span className="stat-desc">{selected.statusReason}</span>}
                </div>
                <div className="stat-card">
                  <span className="stat-label">Fulfilment</span>
                  <span className={`badge ${fulfilmentBadgeClass(selected.fulfilmentStatus)}`}>{humanFulfilment(selected.fulfilmentStatus)}</span>
                </div>
              </div>

              <div className="form-card" style={{ marginTop: "1rem" }}>
                <h3 style={{ fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.5rem" }}>Created</h3>
                <p style={{ color: "var(--text-secondary)" }}>{new Date(selected.createdAt).toLocaleString()}</p>
                <h3 style={{ fontSize: "0.85rem", fontWeight: 600, marginTop: "1rem", marginBottom: "0.5rem" }}>Last updated</h3>
                <p style={{ color: "var(--text-secondary)" }}>{new Date(selected.updatedAt).toLocaleString()}</p>
              </div>

              {selected.status === "CONFIRMED" && (
                <div className="form-card" style={{ marginTop: "1rem" }}>
                  <h3 style={{ fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.75rem" }}>Fulfilment progress</h3>
                  <div className="fulfilment-tracker" role="progressbar" aria-valuenow={FULFILMENT_STEPS.indexOf(selected.fulfilmentStatus) + 1} aria-valuemin={1} aria-valuemax={FULFILMENT_STEPS.length} aria-label="Fulfilment progress">
                    {FULFILMENT_STEPS.map((step, i) => {
                      const currentIdx = FULFILMENT_STEPS.indexOf(selected.fulfilmentStatus);
                      return (
                        <div key={step} className={`fulfilment-step${i <= currentIdx ? " complete" : ""}${i === currentIdx ? " current" : ""}`}>
                          <div className="fulfilment-dot" />
                          <span className="fulfilment-label">{humanFulfilment(step)}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="form-card" style={{ marginTop: "1rem" }}>
                <h3 style={{ fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.75rem" }}>Line items</h3>
                <div className="table-container">
                  <table className="table">
                    <thead>
                      <tr>
                        <th scope="col">Product</th>
                        <th scope="col">Qty</th>
                        <th scope="col">Unit price</th>
                        <th scope="col">Line total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selected.items.map((item) => (
                        <tr key={item.productId}>
                          <td>{item.productName || item.productId}</td>
                          <td>{item.quantity}</td>
                          <td>{formatCurrency(item.effectiveUnitPrice)}</td>
                          <td style={{ fontWeight: 700 }}>{formatCurrency(item.lineTotal)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="order-summary-card" style={{ marginTop: "0.75rem" }}>
                  <div className="summary-row">
                    <span>Subtotal</span>
                    <strong>{formatCurrency(selected.subtotal)}</strong>
                  </div>
                  {Number(selected.discountTotal) > 0 && (
                    <div className="summary-row">
                      <span>Discount</span>
                      <strong>&minus;{formatCurrency(selected.discountTotal)}</strong>
                    </div>
                  )}
                  <div className="summary-row total">
                    <span>Order total</span>
                    <strong>{formatCurrency(selected.totalAmount)}</strong>
                  </div>
                </div>
              </div>

              <div style={{ display: "flex", gap: "0.75rem", marginTop: "1.5rem", flexWrap: "wrap" }}>
                {selected.status === "CONFIRMED" && NEXT_STATUS[selected.fulfilmentStatus] && (
                  <button
                    className="btn"
                    style={{ flex: 1 }}
                    disabled={busy === selected.orderId}
                    onClick={() => void progressOrder(selected)}
                  >
                    {busy === selected.orderId
                      ? "Updating..."
                      : ACTION_LABELS[NEXT_STATUS[selected.fulfilmentStatus]!]}
                  </button>
                )}
                <button
                  className="btn btn-secondary"
                  style={{ flex: 1 }}
                  disabled={downloadingId === selected.orderId}
                  onClick={() => void downloadSummary(selected.orderId)}
                >
                  {downloadingId === selected.orderId ? "Preparing..." : "Download Summary"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
