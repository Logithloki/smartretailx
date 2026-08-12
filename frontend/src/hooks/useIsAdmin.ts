import { useAuth } from "../context/useAuth";
import { isAdminProfile } from "../auth/roles";

export function useIsAdmin(): boolean {
  const auth = useAuth();
  return isAdminProfile(auth.user?.profile);
}
