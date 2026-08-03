import { FormEvent, useEffect, useMemo, useState } from "react";
import { useAuth } from "react-oidc-context";
import { useNavigate } from "react-router-dom";
import { apiFetch, ApiError } from "../api/client";
import type {
  CreateOrderRequest,
  Order,
  Product,
  ProductListResponse,
} from "../api/types";

/*
 * Place-order page (backlog item 27, marking brief Task 3).
 *
 * Flow the demo will walk through at viva:
 *   1. Page loads -> GET /v1/products (public read, still needs JWT).
 *   2. User picks a product and quantity.
 *   3. Submit -> POST /v1/orders with:
 *        - items: [{productId, quantity, unitPrice}]
 *        - Idempotency-Key header (crypto.randomUUID) so a double-
 *          click or a network retry cannot double-charge (backlog
 *          item Order Service idempotency; W2 D4).
 *   4. 201 -> redirect to /orders (the My Orders page opens a
 *      WebSocket and watches this order flip PENDING -> CONFIRMED /
 *      REJECTED live via EventBridge Pipes -> push Lambda).
 *
 * NB - the current backend accepts client-supplied unitPrice, which
 * IS a tampering vector (a malicious client could send 0.01). This
 * SPA is honest and sends the true product price. The correct fix is
 * a backend enhancement to look up product prices by productId
 * inside Order Service create_order; tracked as a future backlog
 * item, out of scope for W6 SPA work.
 */

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
    // Compute for display only; the server recomputes authoritatively.
    // Decimal-safe arithmetic on strings avoids float drift for the
    // preview: parse cents integer -> multiply -> format back.
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
          unitPrice: selected.price,
        },
      ],
    };

    try {
      const order = await apiFetch<Order>(token, "/v1/orders", {
        method: "POST",
        body,
        idempotent: true,
      });
      // Success - go to My Orders where the WS listener will pick up
      // the CONFIRMED / REJECTED flip in near-real-time.
      navigate(`/orders?highlight=${encodeURIComponent(order.orderId)}`, {
        replace: true,
      });
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : String(err));
      setSubmitting(false);
    }
  }

  if (!products) return <p>Loading products...</p>;
  if (products.length === 0)
    return <p>No products available - ask an admin to add one first.</p>;

  return (
    <section>
      <h1>New order</h1>
      {error && <p className="error">Order failed: {error}</p>}
      <form onSubmit={submit} className="stack">
        <label>
          Product
          <select
            value={form.productId}
            onChange={(e) => setForm({ ...form, productId: e.target.value })}
          >
            {products.map((p) => (
              <option key={p.productId} value={p.productId}>
                {p.productName} — £{p.price}
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

        <p className="meta">
          Preview total (server recomputes): £{total}
        </p>

        <button type="submit" disabled={submitting}>
          {submitting ? "Placing order..." : "Place order"}
        </button>
      </form>
    </section>
  );
}
