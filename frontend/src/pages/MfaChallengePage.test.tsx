import { describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { MfaChallengePage } from "./MfaChallengePage";
import { AuthContext, type AuthApi } from "../auth/AuthContext";

const navigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigate };
});

const submitTotpChallengeMock = vi.fn();
vi.mock("../auth/mfa-service", async () => {
  const actual = await vi.importActual<typeof import("../auth/mfa-service")>("../auth/mfa-service");
  return { ...actual, submitTotpChallenge: (code: string) => submitTotpChallengeMock(code) };
});

function makeAuth(): AuthApi {
  return {
    status: "challenge_totp",
    isLoading: false,
    isAuthenticated: false,
    activeNavigator: null,
    user: null,
    error: null,
    signIn: vi.fn(),
    signinRedirect: vi.fn(),
    removeUser: vi.fn(),
    refreshFromCognito: vi.fn().mockResolvedValue(undefined),
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthContext.Provider value={makeAuth()}>
        <MfaChallengePage />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

describe("MfaChallengePage", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("strips non-digits from the code input", () => {
    renderPage();
    const input = screen.getByLabelText(/authenticator code/i);
    fireEvent.change(input, { target: { value: "12abc3" } });
    expect(input).toHaveValue("123");
  });

  it("disables submit until 6 digits are entered", () => {
    renderPage();
    const btn = screen.getByRole("button", { name: /^verify$/i });
    expect(btn).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/authenticator code/i), {
      target: { value: "12345" },
    });
    expect(btn).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/authenticator code/i), {
      target: { value: "123456" },
    });
    expect(btn).not.toBeDisabled();
  });

  it("submits, refreshes auth, and routes to /products on success", async () => {
    submitTotpChallengeMock.mockResolvedValue(undefined);
    renderPage();
    fireEvent.change(screen.getByLabelText(/authenticator code/i), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^verify$/i }));
    await waitFor(() => expect(submitTotpChallengeMock).toHaveBeenCalledWith("123456"));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/products", { replace: true }));
  });

  it("maps a wrong code to the friendly not-valid message and stays on the page", async () => {
    submitTotpChallengeMock.mockRejectedValue(
      Object.assign(new Error(""), { name: "CodeMismatchException" }),
    );
    renderPage();
    fireEvent.change(screen.getByLabelText(/authenticator code/i), {
      target: { value: "999999" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^verify$/i }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/not valid/i),
    );
    expect(navigate).not.toHaveBeenCalled();
  });
});
