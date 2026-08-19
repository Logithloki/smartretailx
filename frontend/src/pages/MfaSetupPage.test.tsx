import { describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { MfaSetupPage } from "./MfaSetupPage";
import { AuthContext, type AuthApi } from "../auth/AuthContext";

const navigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigate };
});

const beginTotpSetupMock = vi.fn();
const verifyAndActivateTotpMock = vi.fn();
vi.mock("../auth/mfa-service", async () => {
  const actual = await vi.importActual<typeof import("../auth/mfa-service")>("../auth/mfa-service");
  return {
    ...actual,
    beginTotpSetup: () => beginTotpSetupMock(),
    verifyAndActivateTotp: (code: string) => verifyAndActivateTotpMock(code),
  };
});

// Stub the QR code library so we don't actually rasterise anything.
vi.mock("qrcode", () => ({
  default: {
    toDataURL: () => Promise.resolve("data:image/png;base64,QRCODESYNTHETIC"),
  },
}));

function makeAuth(email?: string): AuthApi {
  return {
    status: "authenticated",
    isLoading: false,
    isAuthenticated: true,
    activeNavigator: null,
    user: { access_token: "x", id_token: "y", profile: { email } },
    error: null,
    signIn: vi.fn(),
    signinRedirect: vi.fn(),
    removeUser: vi.fn(),
    refreshFromCognito: vi.fn(),
  };
}

function renderPage(email = "ada@example.com") {
  return render(
    <MemoryRouter>
      <AuthContext.Provider value={makeAuth(email)}>
        <MfaSetupPage />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

describe("MfaSetupPage", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders a QR image and hides the manual key by default", async () => {
    beginTotpSetupMock.mockResolvedValue({
      sharedSecret: "MANUALKEYSYNTHETIC",
      setupUri: "otpauth://totp/SmartRetailX:ada@example.com?secret=…",
    });
    renderPage();
    const img = await screen.findByAltText(/scan this QR code/i);
    expect(img).toHaveAttribute("src", "data:image/png;base64,QRCODESYNTHETIC");
    expect(screen.queryByText(/MANUALKEYSYNTHETIC/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /can't scan/i }));
    expect(screen.getByText(/MANUALKEYSYNTHETIC/)).toBeInTheDocument();
  });

  it("verifies the code, activates MFA, then wipes the secret from the DOM", async () => {
    beginTotpSetupMock.mockResolvedValue({
      sharedSecret: "MANUALKEYSYNTHETIC",
      setupUri: "otpauth://totp/SmartRetailX:ada@example.com?secret=…",
    });
    verifyAndActivateTotpMock.mockResolvedValue(undefined);
    renderPage();
    await screen.findByAltText(/scan this QR code/i);
    fireEvent.change(screen.getByLabelText(/6-digit code/i), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: /verify and enable/i }));
    await waitFor(() => expect(verifyAndActivateTotpMock).toHaveBeenCalledWith("123456"));
    // Success view; the secret + QR are gone.
    await waitFor(() =>
      expect(
        screen.getByText(/multi-factor authentication enabled/i),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText(/MANUALKEYSYNTHETIC/)).toBeNull();
    expect(screen.queryByAltText(/scan this QR code/i)).toBeNull();
  });

  it("surfaces the friendly not-valid message on a wrong code and does not activate", async () => {
    beginTotpSetupMock.mockResolvedValue({
      sharedSecret: "MANUALKEYSYNTHETIC",
      setupUri: "otpauth://totp/SmartRetailX:ada@example.com?secret=…",
    });
    verifyAndActivateTotpMock.mockRejectedValue(
      Object.assign(new Error(""), { name: "CodeMismatchException" }),
    );
    renderPage();
    await screen.findByAltText(/scan this QR code/i);
    fireEvent.change(screen.getByLabelText(/6-digit code/i), {
      target: { value: "999999" },
    });
    fireEvent.click(screen.getByRole("button", { name: /verify and enable/i }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/not valid/i),
    );
    // The success view must not appear.
    expect(screen.queryByText(/multi-factor authentication enabled/i)).toBeNull();
  });

  it("shows a Try again button when the initial setup call fails", async () => {
    beginTotpSetupMock.mockRejectedValueOnce(
      Object.assign(new Error(""), { name: "NetworkError" }),
    );
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/could not reach/i),
    );
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});
