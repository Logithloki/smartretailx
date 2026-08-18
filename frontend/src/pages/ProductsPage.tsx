import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "../context/useAuth";
import { apiFetch, ApiError } from "../api/client";
import type { Product, ProductListResponse } from "../api/types";
import { useCart } from "../context/CartContext";
import { useOrderStatusStream, type RealtimeUpdate } from "../hooks/useOrderStatusStream";
import { fetchAuthoritativeProductUpdates } from "./catalogueRefresh";
import { formatCurrency, pricesAreEqual } from "../utils/format";

export function ProductsPage() {
  const auth = useAuth();
  const [products, setProducts] = useState<Product[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cart = useCart();

  // Client-side search and category filtering
  const [search, setSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");

  const applyRealtimeUpdate = useCallback(
    (update: RealtimeUpdate) => {
      const token = auth.user?.access_token;
      if (!token || update.type !== "catalogue.price-refresh") return;
      void fetchAuthoritativeProductUpdates(token, update.productIds)
        .then((authoritative) => {
          setProducts((current) => {
            if (update.productIds.length === 0 || current === null) return authoritative;
            const byId = new Map(authoritative.map((product) => [product.productId, product]));
            const merged = current.map((product) => byId.get(product.productId) ?? product);
            const known = new Set(current.map((product) => product.productId));
            return [...merged, ...authoritative.filter((product) => !known.has(product.productId))];
          });
          setError(null);
        })
        .catch((err: unknown) => {
          setError(err instanceof ApiError ? err.message : String(err));
        });
    },
    [auth.user?.access_token],
  );

  useOrderStatusStream(auth.user?.access_token, applyRealtimeUpdate);

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

  // Derived category list
  const categories = useMemo(() => {
    if (!products) return [];
    const set = new Set<string>();
    for (const p of products) {
      if (p.category) set.add(p.category);
    }
    return Array.from(set).sort();
  }, [products]);

  // Filtered products list
  const filteredProducts = useMemo(() => {
    if (!products) return [];
    return products.filter((p) => {
      const matchesSearch =
        search.trim() === "" ||
        p.productName.toLowerCase().includes(search.toLowerCase()) ||
        p.category.toLowerCase().includes(search.toLowerCase()) ||
        p.productId.toLowerCase().includes(search.toLowerCase());
      const matchesCat =
        selectedCategory === "all" || p.category === selectedCategory;
      return matchesSearch && matchesCat;
    });
  }, [products, search, selectedCategory]);

  if (error) {
    return (
      <div className="alert-error">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        Failed to load product catalogue: {error}
      </div>
    );
  }

  if (!products) {
    return (
      <div className="loading-screen">
        <div className="spinner"></div>
        <p>Loading live product catalogue from API Gateway...</p>
      </div>
    );
  }

  return (
    <section>
      <div className="page-header">
        <div className="page-title-group">
          <h1>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
            Product Catalogue
          </h1>
          <p>Browse verified items in stock across SmartRetailX microservices.</p>
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <span className="stat-label">Total Products</span>
          <span className="stat-value">{products.length}</span>
          <span className="stat-desc">Available in inventory</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Categories</span>
          <span className="stat-value">{categories.length}</span>
          <span className="stat-desc">Distinct product categories</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Filtered Match</span>
          <span className="stat-value">{filteredProducts.length}</span>
          <span className="stat-desc">Items matching query</span>
        </div>
      </div>

      <div className="toolbar">
        <div className="search-input-wrap">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input
            type="text"
            placeholder="Search by name or category..."
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
            {categories.map((c) => (
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
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          </div>
          <h3>No products match your search</h3>
          <p>Try clearing filters or searching for a different keyword.</p>
          <button
            className="btn btn-secondary"
            style={{ marginTop: "1rem" }}
            onClick={() => {
              setSearch("");
              setSelectedCategory("all");
            }}
          >
            Reset Filters
          </button>
        </div>
      ) : (
        <div className="product-grid">
          {filteredProducts.map((p) => (
            <div key={p.productId} className="product-card">
              <div className="product-card-header">
                <h2>{p.productName}</h2>
                <span className="category-tag">{p.category}</span>
              </div>
              <div className="price">{formatCurrency(p.effectivePrice ?? p.price)}</div>
              {p.effectivePrice && !pricesAreEqual(p.effectivePrice, p.price) && (
                <div>
                  <s>{formatCurrency(p.price)}</s>{" "}
                  <span className="badge badge-confirmed">Promotion</span>
                </div>
              )}
              <p className="description">
                {p.description || "High quality inventory item tracked in SmartRetailX catalog."}
              </p>
              <div className="product-card-footer" style={{ justifyContent: "flex-end" }}>
                <button className="btn btn-sm" disabled={!p.active} onClick={() => cart.add(p)}>
                  {p.active ? "Add to cart" : "Unavailable"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

