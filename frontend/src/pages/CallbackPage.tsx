import { useEffect } from "react";
import { useAuth } from "../context/useAuth";
import { useNavigate } from "react-router-dom";

/*
 * react-oidc-context intercepts the ?code=<...> redirect back from
 * Cognito automatically and completes the /token exchange before any
 * child component sees the URL. That means this page usually just
 * flashes for a few milliseconds before we navigate away.
 *
 * If the exchange failed (e.g. code reuse after a refresh), auth.error
 * is set and we surface the message here rather than throw a blank
 * "Loading..." forever.
 */
export function CallbackPage() {
  const auth = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (auth.isAuthenticated) navigate("/products", { replace: true });
  }, [auth.isAuthenticated, navigate]);

  if (auth.error) return <p>Sign-in error: {auth.error.message}</p>;
  return <p>Completing sign-in...</p>;
}
