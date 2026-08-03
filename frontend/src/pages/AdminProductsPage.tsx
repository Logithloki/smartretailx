import { FormEvent, useEffect, useState } from "react";
import { useAuth } from "react-oidc-context";
import { apiFetch, ApiError } from "../api/client";
import type {
  Product,
  ProductCreate,
  ProductListResponse,
  ProductUpdate,
} from "../api/types";

/*
 * Admin products CRUD (backlog item 28).
 *
 * Backend surface:
 *   GET    /v1/products              (already public read)
 *   POST   /v1/products              (admin) full record
 *   PUT    /v1/products/{id}         (admin) PARTIAL update - the
 *                                    Pydantic schema (ProductUpdate)
 *                                    has all fields optional so we
 *                                    can send just the changed keys
 *   DELETE /v1/products/{id}         (admin)
 *
 * RBAC: this whole page is behind AdminRoute (App.tsx). Backend still
 * enforces requires("admin") on every write path independently, so a
 * SPA-layer bypass would still 401 at the JWT authoriser + service
 * middleware.
 *
 * State model: one canonical list, an optional "editing" record. The
 * form UI toggles between create-mode and edit-mode on the same
 * component - keeps the DOM shape stable and avoids the "form
 * unmounts, loses focus" bug that separate render trees usually cause.
 */

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
        // Partial update: only send fields that changed. For a Week 6
        // scope this is a tiny helper; a bigger app would diff against
        // the original list entry. Sending everything is also legal
        // because ProductUpdate is a partial - keeping it simple.
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

  if (!products) return <p>Loading products...</p>;

  return (
    <section>
      <h1>Admin — products</h1>
      {error && <p className="error">{error}</p>}

      <form onSubmit={submit} className="stack">
        <h2>{editingId ? `Edit ${editingId}` : "New product"}</h2>
        <label>
          Product ID (alphanumerics / . _ -)
          <input
            required
            pattern="[A-Za-z0-9._-]+"
            maxLength={100}
            value={draft.productId}
            disabled={!!editingId}
            onChange={(e) => setDraft({ ...draft, productId: e.target.value })}
          />
        </label>
        <label>
          Name
          <input
            required
            maxLength={200}
            value={draft.productName}
            onChange={(e) =>
              setDraft({ ...draft, productName: e.target.value })
            }
          />
        </label>
        <label>
          Price (£, up to 2 decimal places)
          <input
            required
            inputMode="decimal"
            pattern="^\d+(\.\d{1,2})?$"
            value={draft.price}
            onChange={(e) => setDraft({ ...draft, price: e.target.value })}
          />
        </label>
        <label>
          Category
          <input
            required
            maxLength={60}
            value={draft.category}
            onChange={(e) => setDraft({ ...draft, category: e.target.value })}
          />
        </label>
        <label>
          Description (optional)
          <textarea
            maxLength={2000}
            rows={3}
            value={draft.description ?? ""}
            onChange={(e) =>
              setDraft({ ...draft, description: e.target.value })
            }
          />
        </label>
        <div className="actions">
          <button type="submit" disabled={busy}>
            {busy ? "Saving..." : editingId ? "Save changes" : "Create product"}
          </button>
          {editingId && (
            <button type="button" onClick={cancelEdit}>
              Cancel
            </button>
          )}
        </div>
      </form>

      <h2 style={{ marginTop: "2rem" }}>Existing products</h2>
      {products.length === 0 ? (
        <p>None yet.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Category</th>
              <th>Price</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {products.map((p) => (
              <tr key={p.productId}>
                <td>
                  <code>{p.productId}</code>
                </td>
                <td>{p.productName}</td>
                <td>{p.category}</td>
                <td>£{p.price}</td>
                <td>
                  <div className="actions">
                    <button onClick={() => startEdit(p)}>Edit</button>
                    <button
                      className="danger"
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
      )}
    </section>
  );
}
