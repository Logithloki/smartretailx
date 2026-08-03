import { Link, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "react-oidc-context";
import { ProductsPage } from "./pages/ProductsPage";
import { CallbackPage } from "./pages/CallbackPage";

/*
 * The app is deliberately tiny at Week 5 D4 - the "auth end-to-end
 * proven" milestone from the lecturer ruling H.2 is:
 *
 *   1. click a Login button
 *   2. Cognito Hosted UI shows
 *   3. after login the SPA renders GET /v1/products with the bearer
 *      token attached
 *
 * If that works, the whole SPA <-> Cognito <-> HTTP API <-> ECS chain
 * is proven. W6 D1-3 fills out CRUD pages against this skeleton
 * (backlog items 28-30).
 */
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const auth = useAuth();

  if (auth.isLoading) return <p>Loading auth session...</p>;
  if (auth.error) return <p>Auth error: {auth.error.message}</p>;

  if (!auth.isAuthenticated) {
    // signinRedirect kicks off authorization-code + PKCE. The browser
    // is sent to <authority>/oauth2/authorize with code_challenge=...;
    // Cognito's Hosted UI takes over from there and redirects back to
    // redirect_uri with ?code=<one-time>.
    auth.signinRedirect();
    return <p>Redirecting to sign-in...</p>;
  }

  return <>{children}</>;
}

export default function App() {
  const auth = useAuth();

  return (
    <div className="app">
      <header className="app-header">
        <Link to="/" className="brand">
          SmartRetailX
        </Link>
        <nav>
          <Link to="/products">Products</Link>
          {auth.isAuthenticated ? (
            <button
              onClick={() =>
                void auth.signoutRedirect({ post_logout_redirect_uri: window.location.origin })
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
          <Route path="*" element={<p>Not found</p>} />
        </Routes>
      </main>
    </div>
  );
}
