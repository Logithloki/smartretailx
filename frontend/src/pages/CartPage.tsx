import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, ApiError } from "../api/client";
import type { AvailabilityResponse, Order } from "../api/types";
import { useAuth } from "../context/useAuth";
import { useCart, type CartLine } from "../context/CartContext";
import { formatCurrency } from "../utils/format";

export type StockTier = "out" | "low" | "ok" | "unknown";

export const LOW_STOCK_THRESHOLD = 5;

// eslint-disable-next-line react-refresh/only-export-components
export function stockLevel(
  productId: string,
  availability: Record<string, number>,
): StockTier {
  const qty = availability[productId];
  if (qty === undefined) return "unknown";
  if (qty <= 0) return "out";
  if (qty <= LOW_STOCK_THRESHOLD) return "low";
  return "ok";
}

// eslint-disable-next-line react-refresh/only-export-components
export function validateAvailability(
  lines: CartLine[],
  availability: Record<string, number>,
): string | null {
  for (const line of lines) {
    const available = availability[line.product.productId];
    if (available === undefined) {
      return `Availability could not be confirmed for ${line.product.productName}. Please try again.`;
    }
    if (available <= 0) {
      return `${line.product.productName} is out of stock.`;
    }
    if (line.quantity > available) {
      return `${line.product.productName} has only ${available} units available.`;
    }
  }
  return null;
}

const STOCK_BADGE_LABEL: Record<StockTier, string> = {
  out: "Out of stock",
  low: "Low stock",
  ok: "In stock",
  unknown: "Not checked",
};

export function CartPage() {
  const auth = useAuth();
  const token = auth.user?.access_token;
  const cart = useCart();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState<Order | null>(null);
  const [availability, setAvailability] = useState<Record<string, number>>({});
  const advisoryTotal = useMemo(
    () =>
      cart.lines.reduce(
        (sum, line) =>
          sum +
          Math.round(
            Number(line.product.effectivePrice ?? line.product.price) * 100,
          ) *
            line.quantity,
        0,
      ) / 100,
    [cart.lines],
  );

  async function refreshAvailability(): Promise<Record<string, number>> {
    if (!token || cart.lines.length === 0) return {};
    const query = cart.lines
      .map(
        (line) =>
          `productIds=${encodeURIComponent(line.product.productId)}`,
      )
      .join("&");
    const data = await apiFetch<AvailabilityResponse>(
      token,
      `/v1/availability?${query}`,
    );
    const latest = Object.fromEntries(
      data.availability.map((item) => [item.productId, item.quantity]),
    );
    setAvailability(latest);
    return latest;
  }

  async function checkout(): Promise<void> {
    if (!token || cart.lines.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const latestAvailability = await refreshAvailability();
      const availabilityError = validateAvailability(
        cart.lines,
        latestAvailability,
      );
      if (availabilityError) {
        setError(availabilityError);
        return;
      }
      const order = await apiFetch<Order>(token, "/v1/orders", {
        method: "POST",
        idempotent: true,
        body: {
          items: cart.lines.map((line) => ({
            productId: line.product.productId,
            quantity: line.quantity,
          })),
        },
      });
      setConfirmed(order);
      cart.clear();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function stockBadge(productId: string): React.ReactNode {
    const tier = stockLevel(productId, availability);
    const qty = availability[productId];
    return (
      <span className={`badge stock-badge-${tier}`}>
        {STOCK_BADGE_LABEL[tier]}
        {tier !== "unknown" && qty !== undefined && (
          <span className="stock-qty"> ({qty})</span>
        )}
      </span>
    );
  }

  if (confirmed)
    return (
      <section className="form-card">
        <h1>Order confirmed</h1>
        <p>
          Order <code>{confirmed.orderId}</code> was accepted for stock
          reservation.
        </p>
        <div className="summary-row">
          <span>Subtotal</span>
          <strong>{formatCurrency(confirmed.subtotal)}</strong>
        </div>
        <div className="summary-row">
          <span>Discount</span>
          <strong>&minus;{formatCurrency(confirmed.discountTotal)}</strong>
        </div>
        <div className="summary-row total">
          <span>Authoritative total</span>
          <strong>{formatCurrency(confirmed.totalAmount)}</strong>
        </div>
        <Link className="btn" to="/orders">
          Track delivery
        </Link>
      </section>
    );

  if (cart.lines.length === 0)
    return (
      <section className="empty-state">
        <h1>Your cart is empty</h1>
        <Link className="btn" to="/products">
          Browse products
        </Link>
      </section>
    );

  return (
    <section>
      <div className="page-header">
        <div className="page-title-group">
          <h1>Cart &amp; checkout</h1>
          <p>
            Availability is a current hint; stock is atomically reserved by the
            checkout Saga.
          </p>
        </div>
      </div>

      {error && <div className="alert-error">Checkout failed: {error}</div>}

      <div className="table-container">
        <table className="table">
          <thead>
            <tr>
              <th>Product</th>
              <th>Effective price</th>
              <th>Quantity</th>
              <th>Availability</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {cart.lines.map((line) => {
              const tier = stockLevel(line.product.productId, availability);
              return (
                <tr
                  key={line.product.productId}
                  className={
                    tier === "out"
                      ? "stock-row-out"
                      : tier === "low"
                        ? "stock-row-low"
                        : undefined
                  }
                >
                  <td>{line.product.productName}</td>
                  <td>
                    {formatCurrency(
                      line.product.effectivePrice ?? line.product.price,
                    )}
                  </td>
                  <td>
                    <input
                      aria-label={`Quantity for ${line.product.productName}`}
                      type="number"
                      min={1}
                      max={100}
                      value={line.quantity}
                      onChange={(event) =>
                        cart.setQuantity(
                          line.product.productId,
                          Number(event.target.value),
                        )
                      }
                    />
                  </td>
                  <td>{stockBadge(line.product.productId)}</td>
                  <td>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => cart.remove(line.product.productId)}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="order-summary-card" style={{ marginTop: "1rem" }}>
        <div className="summary-row total">
          <span>Advisory cart total</span>
          <strong>{formatCurrency(advisoryTotal)}</strong>
        </div>
        <p>
          Final subtotal, discount and total come from the Order Service
          response.
        </p>
        <button
          className="btn btn-secondary"
          onClick={() => void refreshAvailability()}
        >
          Check availability
        </button>{" "}
        <button
          className="btn"
          disabled={busy}
          onClick={() => void checkout()}
        >
          {busy ? "Submitting…" : "Confirm order"}
        </button>
      </div>
    </section>
  );
}
