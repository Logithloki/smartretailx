export interface IdentityProfile {
  "cognito:groups"?: unknown;
  [claim: string]: unknown;
}

export function isAdminProfile(profile: IdentityProfile | undefined): boolean {
  const groups = profile?.["cognito:groups"];
  return Array.isArray(groups) && groups.includes("admin");
}
