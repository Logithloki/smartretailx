import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { SmartRetailAuthProvider, AuthContext } from "./AuthContext";
import { useContext } from "react";
import type { RuntimeConfig } from "../config/runtime-config";

const signInMock = vi.fn();
const signOutMock = vi.fn();
const fetchAuthSessionMock = vi.fn();
const getCurrentUserMock = vi.fn();

vi.mock("aws-amplify/auth", () => ({
  signIn: (...args: unknown[]) => signInMock(...args),
  signOut: (...args: unknown[]) => signOutMock(...args),
  fetchAuthSession: (...args: unknown[]) => fetchAuthSessionMock(...args),
  getCurrentUser: (...args: unknown[]) => getCurrentUserMock(...args),
}));

vi.mock("./amplify-setup", () => ({ configureAmplify: vi.fn() }));

const config: RuntimeConfig = {
  cognitoAuthority: "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_QutfhUEHK",
  cognitoClientId: "client123",
} as RuntimeConfig;

function wrapper({ children }: { children: ReactNode }) {
  return <SmartRetailAuthProvider config={config}>{children}</SmartRetailAuthProvider>;
}

function useAuthCtx() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("no context");
  return ctx;
}

describe("AuthContext.signIn", () => {
  beforeEach(() => {
    // resetAllMocks (not clearAllMocks) also wipes implementations so queued
    // once-values do not leak between tests.
    vi.resetAllMocks();
    // Default: no existing session on initial hydration.
    fetchAuthSessionMock.mockResolvedValue({ tokens: undefined });
  });

  it("recovers from a stale UserAlreadyAuthenticatedException by signing out and retrying once", async () => {
    signInMock
      .mockRejectedValueOnce(
        Object.assign(new Error("already"), { name: "UserAlreadyAuthenticatedException" }),
      )
      .mockResolvedValueOnce({ isSignedIn: true, nextStep: { signInStep: "DONE" } });
    signOutMock.mockResolvedValue(undefined);
    // Initial mount hydration finds no session; the post-retry hydration finds one.
    fetchAuthSessionMock
      .mockResolvedValueOnce({ tokens: undefined })
      .mockResolvedValue({
        tokens: {
          accessToken: { toString: () => "acc" },
          idToken: { toString: () => "id", payload: { email: "a@b.com", sub: "s" } },
        },
      });

    const { result } = renderHook(useAuthCtx, { wrapper });
    await waitFor(() => expect(result.current.status).toBe("unauthenticated"));

    await act(async () => {
      await result.current.signIn("a@b.com", "pw");
    });

    expect(signOutMock).toHaveBeenCalledTimes(1);
    expect(signInMock).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(result.current.status).toBe("authenticated"));
  });

  it("rethrows non-recoverable sign-in errors without retrying", async () => {
    signInMock.mockRejectedValue(
      Object.assign(new Error("nope"), { name: "NotAuthorizedException" }),
    );

    const { result } = renderHook(useAuthCtx, { wrapper });
    await waitFor(() => expect(result.current.status).toBe("unauthenticated"));

    let caught: unknown;
    await act(async () => {
      try {
        await result.current.signIn("a@b.com", "wrong");
      } catch (e) {
        caught = e;
      }
    });
    expect(caught).toMatchObject({ name: "NotAuthorizedException" });

    expect(signOutMock).not.toHaveBeenCalled();
    expect(signInMock).toHaveBeenCalledTimes(1);
  });
});
