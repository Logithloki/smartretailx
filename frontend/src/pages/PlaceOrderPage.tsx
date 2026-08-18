import { FormEvent, useEffect, useMemo, useState } from "react";
import { useAuth } from "../context/useAuth";
import { useNavigate } from "react-router-dom";
import { apiFetch, ApiError } from "../api/client";
import type {
  CreateOrderRequest,
  Order,
  Product,
  ProductListResponse,
} from "../api/types";
import { formatCurrency } from "../utils/format";

interface FormState {
  productId: string;
  quantity: number;
}

export function PlaceOrderPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const token = auth.user?.access_token;

  const [products, setProducts] = useState<Product[] | null>(null);
  const [form, setForm] = useState<FormState>({ productId: "", quantity: 1 });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    apiFetch<ProductListResponse>(token, "/v1/products", {
      signal: controller.signal,
    })
      .then((data) => {
        setProducts(data.products);
        if (data.products.length > 0 && !form.productId) {
          setForm((f) => ({ ...f, productId: data.products[0].productId }));
        }
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof ApiError ? err.message : String(err));
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const selected = useMemo(
    () => products?.find((p) => p.productId === form.productId) ?? null,
    [products, form.productId],
  );

  const total = useMemo(() => {
    if (!selected) return "0.00";
    const cents = Math.round(Number(selected.price) * 100) * form.quantity;
    return (cents / 100).toFixed(2);
  }, [selected, form.quantity]);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!token || !selected) return;

    setSubmitting(true);
    setError(null);

    const body: CreateOrderRequest = {
      items: [
        {
          productId: selected.productId,
          quantity: form.quantity,
        },
      ],
    };

    try {
      const order = await apiFetch<Order>(token, "/v1/orders", {
        method: "POST",
        body,
        idempotent: true,
      });
      navigate(`/orders?highlight=${encodeURIComponent(order.orderId)}`, {
        replace: true,
      });
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : String(err));
      setSubmitting(false);
    }
  }

  if (!products) {
    return (
      <div className="loading-screen">
        <div className="spinner"></div>
        <p>Loading available items for checkout...</p>
      </div>
    );
  }

  if (products.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
        </div>
        <h3>No Products Available</h3>
        <p>Ask an administrator to create catalogue items first.</p>
      </div>
    );
  }

  return (
    <section>
      <div className="page-header">
        <div className="page-title-group">
          <h1>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
            New Order Checkout
          </h1>
          <p>Place an order verified with automated idempotency keys & real-time Saga execution.</p>
        </div>
      </div>

      {error && (
        <div className="alert-error">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          Order submission failed: {error}
        </div>
      )}

      <form onSubmit={submit} className="checkout-layout">
        <div className="form-card">
          <h2>Select Item & Quantity</h2>
          <label>
            Product Item
            <select
              value={form.productId}
              onChange={(e) => setForm({ ...form, productId: e.target.value })}
            >
              {products.map((p) => (
                <option key={p.productId} value={p.productId}>
                  {p.productName} — {formatCurrency(p.price)} ({p.category})
                </option>
              ))}
            </select>
          </label>

          <label>
            Quantity
            <input
              type="number"
              min={1}
              max={100}
              value={form.quantity}
              onChange={(e) =>
                setForm({ ...form, quantity: Math.max(1, Number(e.target.value)) })
              }
            />
          </label>

          {selected && (
            <div style={{ marginTop: "0.5rem", padding: "1rem", background: "var(--bg-subtle)", borderRadius: "var(--radius-md)", border: "1px solid var(--border-subtle)" }}>
              <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>{selected.productName}</div>
              <div style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginTop: "0.25rem" }}>
                {selected.description || "Tracked inventory item"}
              </div>
              <div style={{ marginTop: "0.5rem", display: "flex", gap: "0.5rem" }}>
                <span className="category-tag">{selected.category}</span>
                <span className="product-id-pill">ID: {selected.productId}</span>
              </div>
            </div>
          )}
        </div>

        <div className="order-summary-card">
          <h2 style={{ fontSize: "1.1rem", fontWeight: 700 }}>Order Summary</h2>

          <div className="summary-row">
            <span>Selected Product</span>
            <strong style={{ color: "var(--text-primary)" }}>{selected?.productName || "—"}</strong>
          </div>

          <div className="summary-row">
            <span>Unit Price</span>
            <span>{formatCurrency(selected?.price)}</span>
          </div>

          <div className="summary-row">
            <span>Quantity</span>
            <span>× {form.quantity}</span>
          </div>

          <div className="summary-row total">
            <span>Estimated Total</span>
            <span>{formatCurrency(total)}</span>
          </div>

          <div style={{ fontSize: "0.775rem", color: "var(--text-tertiary)", background: "var(--bg-subtle)", padding: "0.75rem", borderRadius: "var(--radius-md)" }}>
            🔒 Includes automated <code>Idempotency-Key</code> header to prevent double charges on retries.
          </div>

          <button type="submit" className="btn btn-lg" disabled={submitting} style={{ width: "100%" }}>
            {submitting ? (
              <>
                <div className="spinner" style={{ width: "16px", height: "16px", borderWidth: "2px" }}></div>
                Processing Order...
              </>
            ) : (
              <>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>
                Confirm & Place Order
              </>
            )}
          </button>
        </div>
      </form>
    </section>
  );
}

