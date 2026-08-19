import { describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SecurityPage } from "./SecurityPage";
import { AuthContext, type AuthApi } from "../auth/AuthContext";

const navigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigate };
});

const loadMfaStatusMock = vi.fn();
const disableTotpMock = vi.fn();
vi.mock("../auth/mfa-service", async () => {
  const actual = await vi.importActual<typeof import("../auth/mfa-service")>("../auth/mfa-service");
  return {
    ...actual,
    loadMfaStatus: () => loadMfaStatusMock(),
    disableTotp: () => disableTotpMock(),
  };
});

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

function renderPage(email?: string) {
  return render(
    <MemoryRouter>
      <AuthContext.Provider value={makeAuth(email)}>
        <SecurityPage />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

describe("SecurityPage", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("shows Disabled status + Set up authenticator when MFA is off", async () => {
    loadMfaStatusMock.mockResolvedValue({ enabled: false, preferred: undefined, raw: {} });
    renderPage("ada@example.com");
    expect(await screen.findByText("Disabled")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /set up authenticator/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /disable mfa/i })).toBeNull();
  });

  it("shows Enabled status + Disable MFA when MFA is on", async () => {
    loadMfaStatusMock.mockResolvedValue({ enabled: true, preferred: "TOTP", raw: {} });
    renderPage("ada@example.com");
    expect(await screen.findByText("Enabled")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /disable mfa/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /set up authenticator/i })).toBeNull();
  });

  it("navigates to /auth/mfa/setup when Set up authenticator is clicked", async () => {
    loadMfaStatusMock.mockResolvedValue({ enabled: false, preferred: undefined, raw: {} });
    renderPage("ada@example.com");
    fireEvent.click(await screen.findByRole("button", { name: /set up authenticator/i }));
    expect(navigate).toHaveBeenCalledWith("/auth/mfa/setup");
  });

  it("requires confirmation before calling disableTotp, then refreshes status", async () => {
    loadMfaStatusMock.mockResolvedValueOnce({ enabled: true, preferred: "TOTP", raw: {} });
    loadMfaStatusMock.mockResolvedValueOnce({ enabled: false, preferred: undefined, raw: {} });
    disableTotpMock.mockResolvedValue(undefined);
    renderPage("ada@example.com");

    fireEvent.click(await screen.findByRole("button", { name: /disable mfa/i }));
    // Confirmation dialog appears.
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    // Clicking Cancel keeps things as they are.
    fireEvent.click(screen.getByRole("button", { name: /^cancel$/i }));
    expect(disableTotpMock).not.toHaveBeenCalled();

    // Re-open + confirm inside the alertdialog scope.
    fireEvent.click(screen.getByRole("button", { name: /disable mfa/i }));
    const dialog = screen.getByRole("alertdialog");
    const { getByRole: getInDialog } = within(dialog);
    fireEvent.click(getInDialog("button", { name: /disable mfa/i }));
    await waitFor(() => expect(disableTotpMock).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(/now disabled/i),
    );
  });

  it("hides Enable button and shows CI notice when the account matches the CI pattern", async () => {
    loadMfaStatusMock.mockResolvedValue({ enabled: false, preferred: undefined, raw: {} });
    renderPage("ci-customer-test@example.com");
    await waitFor(() => expect(screen.getByText(/Disabled/)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /set up authenticator/i })).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent(
      /dedicated CI automation account/i,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      /usability guard, not a security boundary/i,
    );
  });

  it("shows the lost-authenticator recovery text without any bypass option", async () => {
    loadMfaStatusMock.mockResolvedValue({ enabled: true, preferred: "TOTP", raw: {} });
    renderPage("ada@example.com");
    await waitFor(() => expect(screen.getByText(/Lost your authenticator/i)).toBeInTheDocument());
    expect(screen.getByText(/contact a SmartRetailX administrator/i)).toBeInTheDocument();
    // Never surface a bypass affordance.
    expect(screen.queryByRole("button", { name: /skip.*mfa/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /master.*code/i })).toBeNull();
    expect(screen.queryByText(/self-service bypass/i)).toBeInTheDocument();
  });
});
