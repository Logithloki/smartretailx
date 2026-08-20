import { Link, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./context/useAuth";
import { LandingPage } from "./pages/LandingPage";
import { ProductsPage } from "./pages/ProductsPage";
import { CallbackPage } from "./pages/CallbackPage";
import { PlaceOrderPage } from "./pages/PlaceOrderPage";
import { CartPage } from "./pages/CartPage";
import { MyOrdersPage } from "./pages/MyOrdersPage";
import { AdminProductsPage } from "./pages/AdminProductsPage";
import { AdminStockPage } from "./pages/AdminStockPage";
import { AdminUsersPage } from "./pages/AdminUsersPage";
import { AdminFulfilmentPage } from "./pages/AdminFulfilmentPage";
import { AdminPromotionsPage } from "./pages/AdminPromotionsPage";
import { SignInPage } from "./pages/SignInPage";
import { SignUpPage } from "./pages/SignUpPage";
import { VerifyEmailPage } from "./pages/VerifyEmailPage";
import { ForgotPasswordPage } from "./pages/ForgotPasswordPage";
import { ResetPasswordPage } from "./pages/ResetPasswordPage";
import { ProfilePage } from "./pages/ProfilePage";
import { MfaSetupPage } from "./pages/MfaSetupPage";
import { MfaChallengePage } from "./pages/MfaChallengePage";
import { OrderDetailPage } from "./pages/OrderDetailPage";
import { useIsAdmin } from "./hooks/useIsAdmin";
import { useCart } from "./context/CartContext";
import { createCognitoLogoutUrl } from "./auth-config";
import { getRuntimeConfig } from "./config/runtime-config";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const auth = useAuth();

  if (auth.isLoading) {
    return (
      <div className="loading-screen">
        <div className="spinner"></div>
        <p>Verifying authentication session...</p>
      </div>
    );
  }

  if (auth.error) {
    return (
      <div className="empty-state">
        <div className="alert-error">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          Auth session error: {auth.error.message}
        </div>
        <button onClick={() => void auth.signinRedirect()}>Re-authenticate</button>
      </div>
    );
  }

  if (!auth.isAuthenticated) {
    return <SignInPage />;
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
        <div className="empty-state">
          <div className="alert-error">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            Access Restricted: This view requires Administrator privileges (`admin` Cognito group).
          </div>
          <Link to="/products" className="btn btn-secondary">Return to Catalogue</Link>
        </div>
      )}
    </ProtectedRoute>
  );
}

export default function App() {
  const auth = useAuth();
  const isAdmin = useIsAdmin();
  const location = useLocation();
  const { itemCount: cartItemCount } = useCart();

  const userEmail = auth.user?.profile.email as string | undefined;

  async function signOut(): Promise<void> {
    await auth.removeUser();
    window.location.assign(createCognitoLogoutUrl(getRuntimeConfig()));
  }

  if (auth.isLoading) {
    return (
      <div className="loading-screen" style={{ minHeight: "100vh" }}>
        <div className="spinner"></div>
        <p>Verifying authentication session...</p>
      </div>
    );
  }

  if (!auth.isAuthenticated) {
    // PR B: unauthenticated users need access to the whole set of public
    // auth routes (sign in / sign up / verify email / forgot / reset), not
    // just the sign-in page.  Route on URL rather than forcing SignInPage
    // regardless.
    return (
      <div className="app">
        <main className="app-main">
          <Routes>
            {/* Public marketing landing page — the front door of the site. */}
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<SignInPage />} />
            <Route path="/signup" element={<SignUpPage />} />
            <Route path="/verify-email" element={<VerifyEmailPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />
            {/* MFA challenge/setup during sign-in: the user is not yet
                fully authenticated, but Amplify is holding a pending
                session. */}
            <Route path="/auth/mfa" element={<MfaChallengePage />} />
            <Route path="/auth/mfa/setup" element={<MfaSetupPage />} />
            <Route path="/callback" element={<CallbackPage />} />
            {/* Everything else (deep links into the authenticated app) sends
                the visitor through the sign-in flow first. */}
            <Route path="*" element={<SignInPage />} />
          </Routes>
        </main>
      </div>
    );
  }

  // The landing page brings its own public header + footer; the internal
  // app chrome would double up on "/" and clash with the marketing layout.
  const isLandingRoute = location.pathname === "/";

  return (
    <div className="app">
      {!isLandingRoute && (
      <header className="app-header">
        <div className="header-left">
          <Link to="/" className="brand">
            SmartRetailX
          </Link>
          <nav>
            <Link
              to="/products"
              className={location.pathname === "/products" ? "active" : ""}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
              Products
            </Link>
            {auth.isAuthenticated && (
              <Link
                to="/cart"
                className={location.pathname === "/cart" ? "active" : ""}
                aria-label={
                  cartItemCount > 0
                    ? `Cart (${cartItemCount} item${cartItemCount === 1 ? "" : "s"})`
                    : "Cart (empty)"
                }
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
                Cart
                {cartItemCount > 0 && (
                  <span className="cart-badge" aria-hidden="true">
                    {cartItemCount > 99 ? "99+" : cartItemCount}
                  </span>
                )}
              </Link>
            )}
            {auth.isAuthenticated && (
              <Link
                to="/orders"
                className={location.pathname === "/orders" ? "active" : ""}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
                My Orders
              </Link>
            )}
            {isAdmin && (
              <Link
                to="/admin/promotions"
                className={location.pathname === "/admin/promotions" ? "active" : ""}
              >
                Admin: Promotions
              </Link>
            )}
            {isAdmin && (
              <Link
                to="/admin/fulfilment"
                className={location.pathname === "/admin/fulfilment" ? "active" : ""}
              >
                Admin: Fulfilment
              </Link>
            )}
            {isAdmin && (
              <Link
                to="/admin/products"
                className={location.pathname === "/admin/products" ? "active" : ""}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
                Admin: Products
              </Link>
            )}
            {isAdmin && (
              <Link
                to="/admin/stock"
                className={location.pathname === "/admin/stock" ? "active" : ""}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
                Admin: Stock
              </Link>
            )}
            {isAdmin && (
              <Link
                to="/admin/users"
                className={location.pathname === "/admin/users" ? "active" : ""}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                Admin: Users
              </Link>
            )}
          </nav>
        </div>

        <div className="header-user">
          {auth.isAuthenticated ? (
            <>
              <div className="user-badge">
                <span>{userEmail ?? "Authenticated User"}</span>
                <span className={`role-pill ${isAdmin ? "admin" : "customer"}`}>
                  {isAdmin ? "Admin" : "Customer"}
                </span>
              </div>
              <Link
                to="/profile"
                className="btn btn-secondary btn-sm"
                aria-label="Profile settings"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                Profile
              </Link>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => void signOut()}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                Sign out
              </button>
            </>
          ) : (
            <button
              className="btn btn-sm"
              onClick={() => auth.signinRedirect()}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
              Sign in
            </button>
          )}
        </div>
      </header>
      )}

      <main className={isLandingRoute ? "app-main app-main-landing" : "app-main"}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
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
            path="/cart"
            element={
              <ProtectedRoute>
                <CartPage />
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
            path="/orders/:orderId"
            element={
              <ProtectedRoute>
                <OrderDetailPage />
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
            path="/admin/promotions"
            element={<AdminRoute><AdminPromotionsPage /></AdminRoute>}
          />
          <Route
            path="/admin/fulfilment"
            element={<AdminRoute><AdminFulfilmentPage /></AdminRoute>}
          />
          <Route
            path="/admin/stock"
            element={
              <AdminRoute>
                <AdminStockPage />
              </AdminRoute>
            }
          />
          <Route
            path="/admin/users"
            element={
              <AdminRoute>
                <AdminUsersPage />
              </AdminRoute>
            }
          />
          <Route
            path="/profile"
            element={
              <ProtectedRoute>
                <ProfilePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/auth/mfa/setup"
            element={
              <ProtectedRoute>
                <MfaSetupPage />
              </ProtectedRoute>
            }
          />
          <Route path="/login" element={<SignInPage />} />
          <Route path="/signup" element={<SignUpPage />} />
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route
            path="*"
            element={
              <div className="empty-state">
                <div className="empty-state-icon">
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                </div>
                <h3>404 Page Not Found</h3>
                <p>The requested URL path does not exist on SmartRetailX.</p>
                <Link to="/products" className="btn btn-secondary" style={{ marginTop: "1rem" }}>
                  Back to Catalogue
                </Link>
              </div>
            }
          />
        </Routes>
      </main>
    </div>
  );
}

