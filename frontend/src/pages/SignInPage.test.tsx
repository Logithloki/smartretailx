import { describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SignInPage } from "./SignInPage";
import { AuthContext, type AuthApi } from "../auth/AuthContext";
import type { SignInOutput } from "aws-amplify/auth";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigateMock };
});

function makeAuth(overrides: Partial<AuthApi> = {}): AuthApi {
  return {
    status: "unauthenticated",
    isLoading: false,
    isAuthenticated: false,
    activeNavigator: null,
    user: null,
    error: null,
    signIn: vi.fn(),
    signinRedirect: vi.fn(),
    removeUser: vi.fn(),
    refreshFromCognito: vi.fn(),
    ...overrides,
  };
}

function renderPage(auth: AuthApi, initialEntry = "/login") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <AuthContext.Provider value={auth}>
        <SignInPage />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

const successResult = {
  isSignedIn: true,
  nextStep: { signInStep: "DONE" },
} as unknown as SignInOutput;

describe("SignInPage", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders custom SmartRetailX form (not the old Hosted UI CTA)", () => {
    renderPage(makeAuth());
    expect(screen.getByLabelText(/^email$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^sign in$/i })).toBeInTheDocument();
    expect(screen.queryByText(/continue to secure sign in/i)).not.toBeInTheDocument();
  });

  it("refuses submission when either field is empty", async () => {
    const signIn = vi.fn().mockResolvedValue(successResult);
    renderPage(makeAuth({ signIn }));
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/both your email and password/i),
    );
    expect(signIn).not.toHaveBeenCalled();
  });

  it("forwards email + password to auth.signIn on submit", async () => {
    const signIn = vi.fn().mockResolvedValue(successResult);
    renderPage(makeAuth({ signIn }));
    // Type="email" inputs strip leading/trailing whitespace in modern
    // browsers; the trim+lowercase normalisation happens in AuthContext.
    fireEvent.change(screen.getByLabelText(/^email$/i), {
      target: { value: "CUSTOMER@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/^password$/i), {
      target: { value: "hunter2!ABCdef" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(signIn).toHaveBeenCalledTimes(1));
    expect(signIn).toHaveBeenCalledWith("CUSTOMER@example.com", "hunter2!ABCdef");
  });

  it("maps NotAuthorizedException to a friendly generic message", async () => {
    const signIn = vi.fn().mockRejectedValue(
      Object.assign(new Error("cognito internal"), { name: "NotAuthorizedException" }),
    );
    renderPage(makeAuth({ signIn }));
    fireEvent.change(screen.getByLabelText(/^email$/i), { target: { value: "x@y.z" } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert).toHaveTextContent(/email or password.*incorrect/i);
      expect(alert).not.toHaveTextContent(/cognito internal/);
    });
  });

  it("navigates to /auth/mfa on CONFIRM_SIGN_IN_WITH_TOTP_CODE (PR C)", async () => {
    const signIn = vi.fn().mockResolvedValue({
      isSignedIn: false,
      nextStep: { signInStep: "CONFIRM_SIGN_IN_WITH_TOTP_CODE" },
    } as unknown as SignInOutput);
    renderPage(makeAuth({ signIn }));
    fireEvent.change(screen.getByLabelText(/^email$/i), { target: { value: "u@e.com" } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "goodPass1!X" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/auth/mfa"));
  });

  it("navigates to /auth/mfa/setup on CONTINUE_SIGN_IN_WITH_TOTP_SETUP (PR C)", async () => {
    const signIn = vi.fn().mockResolvedValue({
      isSignedIn: false,
      nextStep: { signInStep: "CONTINUE_SIGN_IN_WITH_TOTP_SETUP" },
    } as unknown as SignInOutput);
    renderPage(makeAuth({ signIn }));
    fireEvent.change(screen.getByLabelText(/^email$/i), { target: { value: "u@e.com" } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "goodPass1!X" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/auth/mfa/setup"));
  });

  it("shows a challenge notice for CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED", async () => {
    const signIn = vi.fn().mockResolvedValue({
      isSignedIn: false,
      nextStep: { signInStep: "CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED" },
    } as unknown as SignInOutput);
    renderPage(makeAuth({ signIn }));
    fireEvent.change(screen.getByLabelText(/^email$/i), { target: { value: "u@e.com" } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "goodPass1!X" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(/set a new password/i),
    );
  });

  it("does NOT show the Hosted UI fallback control on the normal /login path", () => {
    renderPage(makeAuth());
    expect(screen.queryByRole("button", { name: /Continue with Hosted UI/i })).toBeNull();
  });

  it("shows the Hosted UI fallback control ONLY when ?fallback=hosted-ui is present", () => {
    renderPage(makeAuth(), "/login?fallback=hosted-ui");
    expect(
      screen.getByRole("button", { name: /Continue with Hosted UI/i }),
    ).toBeInTheDocument();
  });

  it("exposes real Forgot password + Create account links (PR B)", () => {
    renderPage(makeAuth());
    const forgot = screen.getByRole("link", { name: /forgot password/i });
    const create = screen.getByRole("link", { name: /create account/i });
    expect(forgot).toHaveAttribute("href", "/forgot-password");
    expect(create).toHaveAttribute("href", "/signup");
    for (const link of [forgot, create]) {
      expect(link).not.toHaveClass("disabled-link");
      expect(link).not.toHaveAttribute("aria-disabled", "true");
    }
  });

  it("offers a Verify account CTA when Cognito reports UserNotConfirmedException", async () => {
    const signIn = vi.fn().mockRejectedValue(
      Object.assign(new Error(""), { name: "UserNotConfirmedException" }),
    );
    renderPage(makeAuth({ signIn }));
    fireEvent.change(screen.getByLabelText(/^email$/i), {
      target: { value: "unconfirmed@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/^password$/i), {
      target: { value: "Correct-Horse-1!" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /verify account/i })).toBeInTheDocument(),
    );
  });
});
