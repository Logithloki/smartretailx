import { createContext, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  fetchAuthSession,
  getCurrentUser,
  signIn as amplifySignIn,
  signOut as amplifySignOut,
} from "aws-amplify/auth";
import type { SignInOutput } from "aws-amplify/auth";
import { configureAmplify } from "./amplify-setup";
import type { RuntimeConfig } from "../config/runtime-config";
import type { IdentityProfile } from "./roles";

// -----------------------------------------------------------------------------
// Auth state machine
// -----------------------------------------------------------------------------
// The SPA represents every sign-in state Cognito can return, including
// challenge states that have dedicated screens or recovery messaging.
//
//  loading                 - initial hydration on page load / after refresh
//  unauthenticated         - no valid session
//  challenge:*             - Cognito returned a challenge that needs UX
//                            before the user can become authenticated
//  authenticated           - valid Cognito session, tokens available
export type AuthStatus =
  | "loading"
  | "unauthenticated"
  | "challenge_new_password_required"
  | "challenge_totp"
  | "challenge_totp_setup"
  | "challenge_sms"
  | "challenge_email"
  | "authenticated";

// Keep the token and profile shape stable for pages that consume auth state.
export interface AuthUser {
  access_token: string;
  id_token: string;
  profile: IdentityProfile & {
    email?: string;
    sub?: string;
    "cognito:username"?: string;
    "cognito:groups"?: string[];
  };
}

export interface AuthApi {
  status: AuthStatus;
  isLoading: boolean;
  isAuthenticated: boolean;
  activeNavigator: string | null;
  user: AuthUser | null;
  error: Error | null;
  signIn: (email: string, password: string) => Promise<SignInOutput>;
  signinRedirect: () => Promise<void>;
  removeUser: () => Promise<void>;
  refreshFromCognito: () => Promise<void>;
}

const AuthContext = createContext<AuthApi | null>(null);

// -----------------------------------------------------------------------------
// Provider
// -----------------------------------------------------------------------------
export function SmartRetailAuthProvider({
  config,
  children,
}: {
  config: RuntimeConfig;
  children: ReactNode;
}) {
  const configuredRef = useRef(false);
  if (!configuredRef.current) {
    configureAmplify(config);
    configuredRef.current = true;
  }

  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [error, setError] = useState<Error | null>(null);

  const hydrateFromSession = useCallback(async () => {
    try {
      // fetchAuthSession returns tokens if the user has a valid session in
      // storage; Amplify manages the underlying refresh cycle.  Non-existent
      // session throws or returns an empty object depending on the SDK
      // version — treat both as "unauthenticated".
      const session = await fetchAuthSession();
      const accessToken = session.tokens?.accessToken?.toString();
      const idToken = session.tokens?.idToken?.toString();
      if (!accessToken || !idToken) {
        setUser(null);
        setStatus("unauthenticated");
        return;
      }
      const payload = session.tokens?.idToken?.payload as
        | (IdentityProfile & Record<string, unknown>)
        | undefined;
      let profile = (payload ?? {}) as AuthUser["profile"];
      if (!profile.email || !profile.sub) {
        try {
          const current = await getCurrentUser();
          profile = {
            ...profile,
            sub: profile.sub ?? current.userId,
            "cognito:username": profile["cognito:username"] ?? current.username,
          };
        } catch {
          // Ignore — best-effort profile enrichment.
        }
      }
      setUser({ access_token: accessToken, id_token: idToken, profile });
      setStatus("authenticated");
      setError(null);
    } catch (err) {
      setUser(null);
      setStatus("unauthenticated");
      if (err instanceof Error && err.name !== "UserUnAuthenticatedException") {
        // Never log token bodies; the Error object only carries a name.
        setError(err);
      }
    }
  }, []);

  useEffect(() => {
    void hydrateFromSession();
  }, [hydrateFromSession]);

  const signIn = useCallback(
    async (email: string, password: string): Promise<SignInOutput> => {
      setError(null);
      const attempt = (): Promise<SignInOutput> =>
        amplifySignIn({
          username: email.trim().toLowerCase(),
          password,
          options: {
            // Amplify default is USER_SRP_AUTH.  Set it explicitly so a future
            // library change cannot silently regress to plaintext-over-TLS.
            authFlowType: "USER_SRP_AUTH",
          },
        });
      let result: SignInOutput;
      try {
        result = await attempt();
      } catch (err) {
        // Amplify v6 throws UserAlreadyAuthenticatedException when a stale
        // session is still in storage (e.g. a half-finished earlier attempt).
        // This otherwise surfaces as the generic "try again" fallback and
        // strands the user.  Clear the stale session and retry exactly once.
        if ((err as { name?: string } | null)?.name === "UserAlreadyAuthenticatedException") {
          try {
            await amplifySignOut();
          } catch {
            // Best-effort; proceed to retry regardless.
          }
          result = await attempt();
        } else {
          throw err;
        }
      }
      // Amplify returns { isSignedIn, nextStep }.  Map the challenge into
      // our state machine.  Never log the session or challenge parameters.
      if (result.isSignedIn) {
        await hydrateFromSession();
        return result;
      }
      switch (result.nextStep.signInStep) {
        case "CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED":
          setStatus("challenge_new_password_required");
          break;
        case "CONFIRM_SIGN_IN_WITH_TOTP_CODE":
          setStatus("challenge_totp");
          break;
        case "CONTINUE_SIGN_IN_WITH_TOTP_SETUP":
          setStatus("challenge_totp_setup");
          break;
        case "CONFIRM_SIGN_IN_WITH_SMS_CODE":
          setStatus("challenge_sms");
          break;
        case "CONFIRM_SIGN_IN_WITH_EMAIL_CODE":
          setStatus("challenge_email");
          break;
        default:
          // Any unhandled challenge stays as "unauthenticated" for safety —
          // the underlying nextStep.signInStep value is not surfaced to
          // avoid leaking Cognito internals.
          setStatus("unauthenticated");
          setError(
            new Error(
              "SmartRetailX cannot yet complete this authentication challenge in the UI.",
            ),
          );
          break;
      }
      return result;
    },
    [hydrateFromSession],
  );

  const removeUser = useCallback(async (): Promise<void> => {
    try {
      await amplifySignOut();
    } catch {
      // Signing out from an already-signed-out state is not an error.
    }
    setUser(null);
    setStatus("unauthenticated");
    setError(null);
  }, []);

  // Legacy compatibility for `auth.signinRedirect()` call in App.tsx's
  // re-authenticate button; with custom auth we simply reload to the sign-in
  // page instead of redirecting to Hosted UI.
  const signinRedirect = useCallback(async (): Promise<void> => {
    setStatus("unauthenticated");
    setUser(null);
  }, []);

  const value = useMemo<AuthApi>(
    () => ({
      status,
      isLoading: status === "loading",
      isAuthenticated: status === "authenticated",
      activeNavigator: null,
      user,
      error,
      signIn,
      signinRedirect,
      removeUser,
      refreshFromCognito: hydrateFromSession,
    }),
    [status, user, error, signIn, signinRedirect, removeUser, hydrateFromSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export { AuthContext };
