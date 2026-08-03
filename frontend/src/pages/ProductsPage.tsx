import { useEffect, useState } from "react";
import { useAuth } from "react-oidc-context";
import { apiFetch, ApiError } from "../api/client";
import type { Product, ProductListResponse } from "../api/types";

/*
 * Public product catalogue (backlog item 27). This page IS the "auth
 * end-to-end proven" milestone: signed-in user, JWT attached, product
 * list rendered from the backend. The other pages just extend this
 * pattern with CRUD flows (backlog 28-30).
 *
 * All fetch/auth/idempotency logic goes through `apiFetch` so a
 * change to header shape (e.g. adding a correlation-id) happens in
 * one file, not one-per-page.
 */
export function ProductsPage() {
  const auth = useAuth();
  const [products, setProducts] = useState<Product[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = auth.user?.access_token;
    if (!token) return;

    const controller = new AbortController();
    apiFetch<ProductListResponse>(token, "/v1/products", {
      signal: controller.signal,
    })
      .then((data) => setProducts(data.products))
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof ApiError ? err.message : String(err));
      });

    return () => controller.abort();
  }, [auth.user?.access_token]);

  if (error) return <p className="error">Failed to load products: {error}</p>;
  if (!products) return <p>Loading products...</p>;

  return (
    <section>
      <h1>Products</h1>
      <p className="meta">{products.length} product(s) available.</p>
      <ul className="product-list">
        {products.map((p) => (
          <li key={p.productId} className="product-card">
            <h2>{p.productName}</h2>
            <p className="price">£{p.price}</p>
            <p className="category">{p.category}</p>
            {p.description && <p>{p.description}</p>}
            <p className="id">id: {p.productId}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
