import { useEffect, useState } from "react";
import { useAuth } from "react-oidc-context";
import { apiFetch, ApiError } from "../api/client";
import type {
  StockAdjustment,
  StockLevel,
  StockListResponse,
} from "../api/types";

/*
 * Admin stock view + adjust (backlog item 30).
 *
 * Backend surface:
 *   GET   /v1/inventory              (admin) list all levels
 *   PATCH /v1/inventory/{productId}  (admin) absolute set - NOT delta
 *
 * Absolute-set (`quantity = N`) instead of delta (`+10`) was a
 * deliberate design choice in the Inventory Service:
 * two admins each sending "+10" would race, whereas both sending
 * "set to 40" agree. So this page shows the current value and lets
 * the operator type the new absolute value, with an implicit "you
 * are overwriting what you see" confirmation. If the value on the
 * server has drifted since load (another admin adjusted it), our
 * PATCH would silently clobber - documented as an acceptable trade
 * for the demo. A future enhancement would use conditional writes
 * with an If-Match ETag, but that is not on the assignment scope.
 *
 * Whole page is behind AdminRoute; backend also enforces
 * requires("admin") on every endpoint. See inventory-service main.py.
 */
export function AdminStockPage() {
  const auth = useAuth();
  const token = auth.user?.access_token;

  const [stock, setStock] = useState<StockLevel[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);

  const reload = () => {
    if (!token) return;
    apiFetch<StockListResponse>(token, "/v1/inventory")
      .then((data) => {
        setStock(data.stock);
        // Seed the per-row draft to the current server value so an
        // empty textbox on load is not misread as "zero it".
        const seed: Record<string, string> = {};
        for (const item of data.stock) seed[item.productId] = String(item.quantity);
        setDrafts(seed);
      })
      .catch((err: unknown) =>
        setError(err instanceof ApiError ? err.message : String(err)),
      );
  };
  useEffect(reload, [token]);

  async function adjust(productId: string) {
    if (!token) return;
    const raw = drafts[productId] ?? "";
    const parsed = Number.parseInt(raw, 10);
    if (!Number.isFinite(parsed) || parsed < 0) {
      setError(`Invalid quantity for ${productId}: must be a non-negative integer.`);
      return;
    }
    setBusyId(productId);
    setError(null);
    const body: StockAdjustment = { quantity: parsed };
    try {
      await apiFetch<StockLevel>(
        token,
        `/v1/inventory/${encodeURIComponent(productId)}`,
        { method: "PATCH", body },
      );
      reload();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  }

  if (!stock) return <p>Loading stock...</p>;

  return (
    <section>
      <h1>Admin — stock levels</h1>
      <p className="meta">
        Adjustments are absolute sets (e.g. "40") not deltas. Two
        operators typing "40" at the same time agree; two operators
        typing "+10" would race.
      </p>
      {error && <p className="error">{error}</p>}

      {stock.length === 0 ? (
        <p>
          No stock rows yet. Stock is created lazily on the first
          reservation attempt against a product - place an order via the
          Order Service to seed a row, then adjust it here.
        </p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Product ID</th>
              <th>Current</th>
              <th>Set to</th>
              <th>Last update</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {stock.map((s) => (
              <tr key={s.productId}>
                <td>
                  <code>{s.productId}</code>
                </td>
                <td>{s.quantity}</td>
                <td>
                  <input
                    type="number"
                    min={0}
                    max={1_000_000}
                    value={drafts[s.productId] ?? ""}
                    onChange={(e) =>
                      setDrafts({ ...drafts, [s.productId]: e.target.value })
                    }
                    style={{ width: 100 }}
                  />
                </td>
                <td>
                  {s.updatedAt
                    ? new Date(s.updatedAt).toLocaleString()
                    : "—"}
                </td>
                <td>
                  <button
                    onClick={() => adjust(s.productId)}
                    disabled={busyId === s.productId}
                  >
                    {busyId === s.productId ? "Saving..." : "Save"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
