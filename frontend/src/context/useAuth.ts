import { useContext } from "react";
import { AuthContext, type AuthApi } from "../auth/AuthContext";

// The SPA's canonical auth hook.  Historically returned the react-oidc-context
// hook; now returns the custom Cognito-backed context whose shape mirrors the
// same fields (`isAuthenticated`, `isLoading`, `user.access_token`,
// `user.profile`, `signinRedirect`, `removeUser`) so no consumer page needs
// to change.
export function useAuth(): AuthApi {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside SmartRetailAuthProvider");
  }
  return value;
}
