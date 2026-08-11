import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../context/useAuth";
import { apiFetch, ApiError } from "../api/client";
import type {
  Product,
  ProductListResponse,
  StockAdjustment,
  StockLevel,
  StockListResponse,
} from "../api/types";

export interface UnifiedStockItem {
  productId: string;
  productName: string;
  category: string;
  price: string;
  quantity: number;
  updatedAt: string | null;
  hasStockRow: boolean;
}

export function AdminStockPage() {
  const auth = useAuth();
  const token = auth.user?.access_token;

  const [products, setProducts] = useState<Product[] | null>(null);
  const [stockMap, setStockMap] = useState<Record<string, StockLevel>>({});
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const reload = () => {
    if (!token) return;

    // Fetch both Products catalog and Inventory stock levels concurrently
    Promise.all([
      apiFetch<ProductListResponse>(token, "/v1/products"),
      apiFetch<StockListResponse>(token, "/v1/inventory"),
    ])
      .then(([prodData, stockData]) => {
        setProducts(prodData.products);

        const map: Record<string, StockLevel> = {};
        const seedDrafts: Record<string, string> = {};

        for (const item of stockData.stock) {
          map[item.productId] = item;
          seedDrafts[item.productId] = String(item.quantity);
        }

        // For products not yet in stock table, seed draft input with 0
        for (const p of prodData.products) {
          if (seedDrafts[p.productId] === undefined) {
            seedDrafts[p.productId] = "0";
          }
        }

        setStockMap(map);
        setDrafts(seedDrafts);
      })
      .catch((err: unknown) =>
        setError(err instanceof ApiError ? err.message : String(err)),
      );
  };

  useEffect(reload, [token]);

  async function adjust(productId: string) {
    if (!token) return;
    const raw = drafts[productId] ?? "0";
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

  // Combine Products catalog with Inventory rows
  const unifiedItems = useMemo<UnifiedStockItem[]>(() => {
    if (!products) return [];

    return products.map((p) => {
      const stockRow = stockMap[p.productId];
      return {
        productId: p.productId,
        productName: p.productName,
        category: p.category,
        price: p.price,
        quantity: stockRow ? stockRow.quantity : 0,
        updatedAt: stockRow ? stockRow.updatedAt : null,
        hasStockRow: !!stockRow,
      };
    });
  }, [products, stockMap]);

  // Derived metrics
  const stats = useMemo(() => {
    if (!unifiedItems) return { totalItems: 0, totalUnits: 0, lowStock: 0 };
    let totalUnits = 0;
    let lowStock = 0;
    for (const item of unifiedItems) {
      totalUnits += item.quantity;
      if (item.quantity < 10) lowStock++;
    }
    return {
      totalItems: unifiedItems.length,
      totalUnits,
      lowStock,
    };
  }, [unifiedItems]);

  // Filtered stock list
  const filteredItems = useMemo(() => {
    if (!unifiedItems) return [];
    const query = search.trim().toLowerCase();
    if (!query) return unifiedItems;

    return unifiedItems.filter(
      (item) =>
        item.productId.toLowerCase().includes(query) ||
        item.productName.toLowerCase().includes(query) ||
        item.category.toLowerCase().includes(query),
    );
  }, [unifiedItems, search]);

  if (!products) {
    return (
      <div className="loading-screen">
        <div className="spinner"></div>
        <p>Loading Product Catalogue & Aurora PostgreSQL Stock Levels...</p>
      </div>
    );
  }

  return (
    <section>
      <div className="page-header">
        <div className="page-title-group">
          <h1>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
            Admin — Inventory & Stock Control
          </h1>
          <p>Real-time inventory levels synchronized across Aurora PostgreSQL database.</p>
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <span className="stat-label">Catalogue Items</span>
          <span className="stat-value">{stats.totalItems}</span>
          <span className="stat-desc">Products in catalogue</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Total Units On Hand</span>
          <span className="stat-value">{stats.totalUnits}</span>
          <span className="stat-desc">Sum of all inventory stock</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Low Stock Alerts (&lt; 10)</span>
          <span
            className="stat-value"
            style={{ color: stats.lowStock > 0 ? "var(--rose-600)" : "var(--emerald-600)" }}
          >
            {stats.lowStock}
          </span>
          <span className="stat-desc">Items needing replenishment</span>
        </div>
      </div>

      {error && (
        <div className="alert-error">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          Inventory API Error: {error}
        </div>
      )}

      <div className="toolbar">
        <div className="search-input-wrap">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input
            type="text"
            placeholder="Search stock table by name, category, or ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {filteredItems.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
          </div>
          <h3>No Matching Inventory Items Found</h3>
          <p>Try searching for a different product name or category.</p>
        </div>
      ) : (
        <div className="table-container">
          <table className="table">
            <thead>
              <tr>
                <th>Product ID</th>
                <th>Product Name</th>
                <th>Category</th>
                <th>Current Stock</th>
                <th>Set Absolute Quantity</th>
                <th>Last DB Update</th>
                <th style={{ textAlign: "right" }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredItems.map((item) => (
                <tr key={item.productId}>
                  <td>
                    <code>{item.productId}</code>
                  </td>
                  <td style={{ fontWeight: 600 }}>{item.productName}</td>
                  <td>
                    <span className="category-tag">{item.category}</span>
                  </td>
                  <td>
                    <span
                      className={`badge ${
                        item.quantity < 10 ? "badge-rejected" : "badge-confirmed"
                      }`}
                    >
                      {item.quantity} units
                    </span>
                  </td>
                  <td>
                    <input
                      type="number"
                      min={0}
                      max={1000000}
                      value={drafts[item.productId] ?? "0"}
                      onChange={(e) =>
                        setDrafts({ ...drafts, [item.productId]: e.target.value })
                      }
                      style={{ width: "110px" }}
                    />
                  </td>
                  <td style={{ fontSize: "0.825rem", color: "var(--text-tertiary)" }}>
                    {item.updatedAt
                      ? new Date(item.updatedAt).toLocaleString()
                      : "Not initialized"}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => adjust(item.productId)}
                      disabled={busyId === item.productId}
                    >
                      {busyId === item.productId ? (
                        <>
                          <div className="spinner" style={{ width: "12px", height: "12px", borderWidth: "2px" }}></div>
                          Saving...
                        </>
                      ) : (
                        "Save Level"
                      )}
                    </button>
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
