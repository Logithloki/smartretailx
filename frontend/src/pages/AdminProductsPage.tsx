import { FormEvent, useEffect, useMemo, useState } from "react";
import { useAuth } from "../context/useAuth";
import { apiFetch, ApiError } from "../api/client";
import type {
  Product,
  ProductCreate,
  ProductListResponse,
  ProductUpdate,
} from "../api/types";

const emptyDraft: ProductCreate = {
  productId: "",
  productName: "",
  price: "0.00",
  category: "",
  description: "",
};

export function AdminProductsPage() {
  const auth = useAuth();
  const token = auth.user?.access_token;

  const [products, setProducts] = useState<Product[] | null>(null);
  const [draft, setDraft] = useState<ProductCreate>(emptyDraft);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Search and Category Filter
  const [search, setSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");

  const reload = () => {
    if (!token) return;
    apiFetch<ProductListResponse>(token, "/v1/products")
      .then((data) => setProducts(data.products))
      .catch((err: unknown) =>
        setError(err instanceof ApiError ? err.message : String(err)),
      );
  };
  useEffect(reload, [token]);

  function startEdit(p: Product) {
    setEditingId(p.productId);
    setDraft({
      productId: p.productId,
      productName: p.productName,
      price: p.price,
      category: p.category,
      description: p.description ?? "",
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function cancelEdit() {
    setEditingId(null);
    setDraft(emptyDraft);
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!token) return;
    setBusy(true);
    setError(null);

    try {
      if (editingId) {
        const patch: ProductUpdate = {
          productName: draft.productName,
          price: draft.price,
          category: draft.category,
          description: draft.description ?? null,
        };
        await apiFetch<Product>(
          token,
          `/v1/products/${encodeURIComponent(editingId)}`,
          { method: "PUT", body: patch },
        );
      } else {
        await apiFetch<Product>(token, "/v1/products", {
          method: "POST",
          body: draft,
        });
      }
      cancelEdit();
      reload();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(productId: string) {
    if (!token) return;
    if (!window.confirm(`Delete product ${productId}? This cannot be undone.`))
      return;
    try {
      await apiFetch(token, `/v1/products/${encodeURIComponent(productId)}`, {
        method: "DELETE",
      });
      reload();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  // Derived categories
  const categories = useMemo(() => {
    if (!products) return [];
    const set = new Set<string>();
    for (const p of products) if (p.category) set.add(p.category);
    return Array.from(set).sort();
  }, [products]);

  // Filtered list
  const filteredProducts = useMemo(() => {
    if (!products) return [];
    return products.filter((p) => {
      const matchesSearch =
        search.trim() === "" ||
        p.productName.toLowerCase().includes(search.toLowerCase()) ||
        p.productId.toLowerCase().includes(search.toLowerCase()) ||
        p.category.toLowerCase().includes(search.toLowerCase());
      const matchesCat =
        selectedCategory === "all" || p.category === selectedCategory;
      return matchesSearch && matchesCat;
    });
  }, [products, search, selectedCategory]);

  if (!products) {
    return (
      <div className="loading-screen">
        <div className="spinner"></div>
        <p>Loading Admin Products Management suite...</p>
      </div>
    );
  }

  return (
    <section>
      <div className="page-header">
        <div className="page-title-group">
          <h1>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
            Admin — Product Management
          </h1>
          <p>Full CRUD operations on DynamoDB product catalog with server-side RBAC validation.</p>
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <span className="stat-label">Total Products</span>
          <span className="stat-value">{products.length}</span>
          <span className="stat-desc">Registered in Product Service</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Active Categories</span>
          <span className="stat-value">{categories.length}</span>
          <span className="stat-desc">Product classifications</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Mode Status</span>
          <span className="stat-value" style={{ fontSize: "1.1rem" }}>
            {editingId ? `Editing: ${editingId}` : "Create Mode"}
          </span>
          <span className="stat-desc">{editingId ? "Updating existing product" : "Ready for new product"}</span>
        </div>
      </div>

      {error && (
        <div className="alert-error">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          Admin API Error: {error}
        </div>
      )}

      <form onSubmit={submit} className="form-card" style={{ marginBottom: "2.5rem" }}>
        <h2>{editingId ? `Edit Product — ${editingId}` : "Create New Product"}</h2>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "1.25rem" }}>
          <label>
            Product ID
            <input
              required
              pattern="[A-Za-z0-9._-]+"
              maxLength={100}
              placeholder="e.g. macbook-pro-16"
              value={draft.productId}
              disabled={!!editingId}
              onChange={(e) => setDraft({ ...draft, productId: e.target.value })}
            />
          </label>

          <label>
            Product Name
            <input
              required
              maxLength={200}
              placeholder="e.g. Smart Retail Laptop X1"
              value={draft.productName}
              onChange={(e) =>
                setDraft({ ...draft, productName: e.target.value })
              }
            />
          </label>

          <label>
            Price (£ GBP)
            <input
              required
              inputMode="decimal"
              pattern="^\d+(\.\d{1,2})?$"
              placeholder="29.99"
              value={draft.price}
              onChange={(e) => setDraft({ ...draft, price: e.target.value })}
            />
          </label>

          <label>
            Category
            <input
              required
              maxLength={60}
              placeholder="e.g. Electronics"
              value={draft.category}
              onChange={(e) => setDraft({ ...draft, category: e.target.value })}
            />
          </label>
        </div>

        <label>
          Description (Optional)
          <textarea
            maxLength={2000}
            rows={2}
            placeholder="Detailed description of the product..."
            value={draft.description ?? ""}
            onChange={(e) =>
              setDraft({ ...draft, description: e.target.value })
            }
          />
        </label>

        <div className="actions" style={{ justifyContent: "flex-end", marginTop: "0.5rem" }}>
          {editingId && (
            <button type="button" className="btn btn-secondary" onClick={cancelEdit}>
              Cancel Edit
            </button>
          )}
          <button type="submit" className="btn" disabled={busy}>
            {busy ? (
              <>
                <div className="spinner" style={{ width: "16px", height: "16px", borderWidth: "2px" }}></div>
                Saving...
              </>
            ) : editingId ? (
              "Save Changes"
            ) : (
              "Create Product"
            )}
          </button>
        </div>
      </form>

      <div className="toolbar">
        <div className="search-input-wrap">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input
            type="text"
            placeholder="Filter catalog table by name, ID or category..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="filter-group">
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
          >
            <option value="all">All Categories ({products.length})</option>
            {categories.map((c: string) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      </div>

      {filteredProducts.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
          </div>
          <h3>No Products Found</h3>
          <p>Use the form above to add your first product item.</p>
        </div>
      ) : (
        <div className="table-container">
          <table className="table">
            <thead>
              <tr>
                <th>Product ID</th>
                <th>Name</th>
                <th>Category</th>
                <th>Price</th>
                <th style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredProducts.map((p: Product) => (
                <tr key={p.productId}>
                  <td>
                    <code>{p.productId}</code>
                  </td>
                  <td style={{ fontWeight: 600 }}>{p.productName}</td>
                  <td>
                    <span className="category-tag">{p.category}</span>
                  </td>
                  <td style={{ fontWeight: 700 }}>£{p.price}</td>
                  <td style={{ textAlign: "right" }}>
                    <div className="actions" style={{ justifyContent: "flex-end" }}>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => startEdit(p)}
                      >
                        Edit
                      </button>
                      <button
                        className="btn btn-danger btn-sm"
                        onClick={() => remove(p.productId)}
                      >
                        Delete
                      </button>
                    </div>
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

