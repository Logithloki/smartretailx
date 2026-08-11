import type { ReactNode } from "react";
import { AuthProvider } from "react-oidc-context";
import { createAuthConfig } from "../auth-config";
import type { RuntimeConfig } from "../config/runtime-config";

export function SmartRetailAuthProvider({
  config,
  children,
}: {
  config: RuntimeConfig;
  children: ReactNode;
}) {
  return <AuthProvider {...createAuthConfig(config)}>{children}</AuthProvider>;
}
