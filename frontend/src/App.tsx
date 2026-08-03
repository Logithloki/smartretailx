import { Link, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "react-oidc-context";
import { ProductsPage } from "./pages/ProductsPage";
import { CallbackPage } from "./pages/CallbackPage";
import { PlaceOrderPage } from "./pages/PlaceOrderPage";
import { MyOrdersPage } from "./pages/MyOrdersPage";
import { AdminProductsPage } from "./pages/AdminProductsPage";
import { AdminStockPage } from "./pages/AdminStockPage";
import { useIsAdmin } from "./hooks/useIsAdmin";

/*
 * Route map (backlog items 27-30 + lecturer ruling H.2):
 *
 *   /                    -> redirect to /products
 *   /products            (public read) list products
 *   /orders/new          (customer)    place an order
 *   /orders              (customer)    my orders + live WS status
 *   /admin/products      (admin)       products CRUD
 *   /admin/stock         (admin)       stock view/adjust
 *   /callback            OIDC redirect handler
 *
 * ProtectedRoute enforces authentication. AdminRoute enforces admin
 * group membership on top. Both are UI-only conveniences - every
 * admin endpoint independently checks cognito:groups server-side, so
 * a bypass on the SPA gate is meaningless.
 */

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const auth = useAuth();

  if (auth.isLoading) return <p>Loading auth session...</p>;
  if (auth.error) return <p>Auth error: {auth.error.message}</p>;

  if (!auth.isAuthenticated) {
    auth.signinRedirect();
    return <p>Redirecting to sign-in...</p>;
  }

  return <>{children}</>;
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const isAdmin = useIsAdmin();
  return (
    <ProtectedRoute>
      {isAdmin ? (
        children
      ) : (
        <p className="error">
          This page is restricted to administrators. Contact support if
          you believe you should have access.
        </p>
      )}
    </ProtectedRoute>
  );
}

export default function App() {
  const auth = useAuth();
  const isAdmin = useIsAdmin();

  return (
    <div className="app">
      <header className="app-header">
        <Link to="/" className="brand">
          SmartRetailX
        </Link>
        <nav>
          <Link to="/products">Products</Link>
          {auth.isAuthenticated && <Link to="/orders/new">New order</Link>}
          {auth.isAuthenticated && <Link to="/orders">My orders</Link>}
          {isAdmin && <Link to="/admin/products">Admin: products</Link>}
          {isAdmin && <Link to="/admin/stock">Admin: stock</Link>}
          {auth.isAuthenticated ? (
            <button
              onClick={() =>
                void auth.signoutRedirect({
                  post_logout_redirect_uri: window.location.origin,
                })
              }
            >
              Sign out ({auth.user?.profile.email as string | undefined})
            </button>
          ) : (
            <button onClick={() => void auth.signinRedirect()}>Sign in</button>
          )}
        </nav>
      </header>

      <main className="app-main">
        <Routes>
          <Route path="/" element={<Navigate to="/products" replace />} />
          <Route path="/callback" element={<CallbackPage />} />
          <Route
            path="/products"
            element={
              <ProtectedRoute>
                <ProductsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/orders/new"
            element={
              <ProtectedRoute>
                <PlaceOrderPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/orders"
            element={
              <ProtectedRoute>
                <MyOrdersPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/products"
            element={
              <AdminRoute>
                <AdminProductsPage />
              </AdminRoute>
            }
          />
          <Route
            path="/admin/stock"
            element={
              <AdminRoute>
                <AdminStockPage />
              </AdminRoute>
            }
          />
          <Route path="*" element={<p>Not found</p>} />
        </Routes>
      </main>
    </div>
  );
}
