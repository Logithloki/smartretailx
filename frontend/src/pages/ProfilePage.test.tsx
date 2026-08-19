import { render, screen, waitFor, fireEvent, cleanup, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { AuthContext } from "../auth/AuthContext";
import { ProfilePage } from "./ProfilePage";
import { loadMfaStatus, disableTotp, isCiAutomationEmail } from "../auth/mfa-service";
import { loadProfileAttributes, saveProfileAttributes, verifyEmailAttribute } from "../auth/profile-service";
import { changePassword } from "../auth/password-service";
import { AuthApi } from "../auth/AuthContext";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("../auth/mfa-service", () => ({
  loadMfaStatus: vi.fn(),
  disableTotp: vi.fn(),
  isCiAutomationEmail: vi.fn(),
}));

vi.mock("../auth/profile-service", () => ({
  loadProfileAttributes: vi.fn(),
  saveProfileAttributes: vi.fn(),
  verifyEmailAttribute: vi.fn(),
}));

vi.mock("../auth/password-service", () => ({
  changePassword: vi.fn(),
}));

function makeAuth(email?: string, groups?: string[]): AuthApi {
  return {
    status: "authenticated",
    isLoading: false,
    isAuthenticated: true,
    activeNavigator: null,
    user: {
      access_token: "mock-access",
      id_token: "mock-id",
      profile: {
        email: email ?? "test@example.com",
        "cognito:groups": groups ?? [],
      },
    },
    error: null,
    signIn: vi.fn(),
    signinRedirect: vi.fn(),
    removeUser: vi.fn(),
    refreshFromCognito: vi.fn(),
  };
}

describe("ProfilePage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(isCiAutomationEmail).mockReturnValue(false);
    vi.mocked(loadMfaStatus).mockResolvedValue({
      enabled: false,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      preferred: "DISABLED" as any,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      raw: { preferred: "DISABLED" as any, enabled: [] },
    });
    vi.mocked(loadProfileAttributes).mockResolvedValue({
      email: "test@example.com",
      given_name: "Jane",
      family_name: "Smith",
    });
  });

  afterEach(() => {
    cleanup();
  });

  function renderPage(auth = makeAuth()) {
    return render(
      <MemoryRouter>
        <AuthContext.Provider value={auth}>
          <ProfilePage />
        </AuthContext.Provider>
      </MemoryRouter>
    );
  }

  it("loads profile and MFA status on mount", async () => {
    renderPage();

    expect(screen.getByText("Loading profile...")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.queryByText("Loading profile...")).not.toBeInTheDocument();
    });

    // Profile attributes
    expect(screen.getByLabelText("First name")).toHaveValue("Jane");
    expect(screen.getByLabelText("Last name")).toHaveValue("Smith");
    expect(screen.getByLabelText("Email address")).toHaveValue("test@example.com");

    // MFA Status
    expect(screen.getByText("Disabled")).toBeInTheDocument();
  });

  it("updates profile successfully without email change", async () => {
    vi.mocked(saveProfileAttributes).mockResolvedValue({ isUpdated: true });
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText("First name")).toHaveValue("Jane");
    });

    fireEvent.change(screen.getByLabelText("First name"), { target: { value: "Janet" } });
    fireEvent.submit(screen.getByRole("button", { name: "Save Changes" }).closest("form")!);

    expect(screen.getByRole("button", { name: "Saving…" })).toBeInTheDocument();

    await waitFor(() => {
      expect(saveProfileAttributes).toHaveBeenCalledWith({
        email: "test@example.com",
        given_name: "Janet",
        family_name: "Smith",
      });
      expect(screen.getByText("Profile updated successfully.")).toBeInTheDocument();
    });
  });

  it("handles email verification flow", async () => {
    vi.mocked(saveProfileAttributes).mockResolvedValue({
      isUpdated: false,
      nextStep: {
        updateAttributeStep: "CONFIRM_ATTRIBUTE_WITH_CODE",
      },
    });
    vi.mocked(verifyEmailAttribute).mockResolvedValue();

    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText("Email address")).toHaveValue("test@example.com");
    });

    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "new@example.com" } });
    fireEvent.submit(screen.getByRole("button", { name: "Save Changes" }).closest("form")!);

    await waitFor(() => {
      expect(screen.getByText(/verification code has been sent/i)).toBeInTheDocument();
      expect(screen.getByLabelText("Verification Code")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Verification Code"), { target: { value: "123456" } });
    fireEvent.submit(screen.getByRole("button", { name: "Verify Email" }).closest("form")!);

    await waitFor(() => {
      expect(verifyEmailAttribute).toHaveBeenCalledWith("123456");
      expect(screen.getByText("Email verified and profile updated successfully.")).toBeInTheDocument();
      expect(screen.queryByLabelText("Verification Code")).not.toBeInTheDocument();
    });
  });

  it("changes password successfully", async () => {
    vi.mocked(changePassword).mockResolvedValue();
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText("Current password")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "oldPass" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "newPass123!" } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "newPass123!" } });

    fireEvent.submit(screen.getByRole("button", { name: "Update Password" }).closest("form")!);

    await waitFor(() => {
      expect(changePassword).toHaveBeenCalledWith("oldPass", "newPass123!");
      expect(screen.getByText("Password changed successfully.")).toBeInTheDocument();
    });
  });

  it("shows error if passwords do not match", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText("Current password")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "oldPass" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "newPass123!" } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "wrongPass" } });

    fireEvent.submit(screen.getByRole("button", { name: "Update Password" }).closest("form")!);

    await waitFor(() => {
      expect(screen.getByText("New password and confirm password do not match.")).toBeInTheDocument();
    });
  });

  it("disables MFA with confirmation", async () => {
    vi.mocked(loadMfaStatus).mockResolvedValue({
      enabled: true,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      preferred: "TOTP" as any,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      raw: { preferred: "TOTP" as any, enabled: ["TOTP" as any] },
    });
    vi.mocked(disableTotp).mockResolvedValue();

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Enabled")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Disable MFA" }));

    const dialog = screen.getByRole("alertdialog");
    expect(within(dialog).getByText("Disable multi-factor authentication?")).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: "Disable MFA" }));

    await waitFor(() => {
      expect(disableTotp).toHaveBeenCalled();
      expect(screen.getByText("Multi-factor authentication is now disabled.")).toBeInTheDocument();
    });
  });

  it("hides Enable MFA button for CI accounts", async () => {
    vi.mocked(isCiAutomationEmail).mockReturnValue(true);
    renderPage(makeAuth("ci-admin-test@example.com"));

    await waitFor(() => {
      expect(screen.getByText("Disabled")).toBeInTheDocument();
    });

    expect(screen.queryByRole("button", { name: "Set up authenticator" })).not.toBeInTheDocument();
    expect(screen.getByText(/CI automation account/)).toBeInTheDocument();
  });

  it("navigates to /auth/mfa/setup when Set up authenticator is clicked", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Set up authenticator" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Set up authenticator" }));
    expect(navigateMock).toHaveBeenCalledWith("/auth/mfa/setup");
  });

  it("shows lost-authenticator recovery text without any bypass option", async () => {
    vi.mocked(loadMfaStatus).mockResolvedValue({
      enabled: true,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      preferred: "TOTP" as any,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      raw: { preferred: "TOTP" as any, enabled: ["TOTP" as any] },
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/Lost your authenticator/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/contact a SmartRetailX administrator/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /skip.*mfa/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /master.*code/i })).toBeNull();
  });

  it("shows role as read-only for admin users", async () => {
    renderPage(makeAuth("admin@example.com", ["admin"]));

    await waitFor(() => {
      expect(screen.getByText("Admin")).toBeInTheDocument();
    });

    expect(screen.getByText("(Read-only)")).toBeInTheDocument();
  });

  it("shows role as Customer for non-admin users", async () => {
    renderPage(makeAuth("user@example.com", []));

    await waitFor(() => {
      expect(screen.getByText("Customer")).toBeInTheDocument();
    });

    expect(screen.getByText("(Read-only)")).toBeInTheDocument();
  });
});
