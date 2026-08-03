import { useEffect, useState } from "react";
import { useAuth } from "react-oidc-context";
import { API_BASE_URL } from "../auth-config";

interface Product {
  productId: string;
  productName: string;
  price: string;
  category: string;
  description: string | null;
}

interface ProductListResponse {
  products: Product[];
  count: number;
}

/*
 * This page IS the "auth end-to-end proven" milestone. It:
 *   1. Reads the current user's access_token from react-oidc-context
 *   2. Calls GET <API_BASE_URL>/v1/products with Authorization: Bearer
 *   3. Renders the list, or the exact error the backend returned
 *
 * Styling is intentionally minimal. Week 5 D4's goal is proving the
 * chain; product/CRUD UX comes in W6 (backlog items 28-30).
 */
export function ProductsPage() {
  const auth = useAuth();
  const [products, setProducts] = useState<Product[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!auth.user?.access_token) return;

    // AbortController lets React StrictMode's double-invoke in dev not
    // double-fire the real fetch to /v1/products.
    const controller = new AbortController();

    fetch(`${API_BASE_URL}/v1/products`, {
      headers: { Authorization: `Bearer ${auth.user.access_token}` },
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${await res.text()}`);
        }
        return (await res.json()) as ProductListResponse;
      })
      .then((data) => setProducts(data.products))
      .catch((err) => {
        if (err.name !== "AbortError") setError(err.message);
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
