import { useAuth } from "react-oidc-context";

/*
 * Reads the `cognito:groups` claim off the ID token profile and
 * returns whether the caller is in the `admins` group.
 *
 * Important - this is a UI convenience only. The backend enforces the
 * admin check independently on every admin endpoint via
 * `srx_common.auth.requires("admin")` (see e.g. product-service
 * main.py POST /v1/products). A user who edits their own JWT to add
 * the claim gets past the SPA gate but still 401s at API Gateway
 * because Cognito's signature won't verify. This hook exists purely
 * so we don't show admin-only nav links to customers.
 */
export function useIsAdmin(): boolean {
  const auth = useAuth();
  const groups = auth.user?.profile["cognito:groups"];
  if (!Array.isArray(groups)) return false;
  return groups.includes("admins");
}
