import { describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SignUpPage } from "./SignUpPage";

const navigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigate };
});

const amplifySignUp = vi.fn();
vi.mock("aws-amplify/auth", () => ({
  signUp: (args: unknown) => amplifySignUp(args),
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <SignUpPage />
    </MemoryRouter>,
  );
}

describe("SignUpPage", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  function fillValid(overrides: Partial<Record<string, string>> = {}): void {
    const values = {
      firstName: "Ada",
      lastName: "Lovelace",
      email: "ada@example.com",
      password: "Correct-Horse-1!",
      confirm: "Correct-Horse-1!",
      ...overrides,
    };
    fireEvent.change(screen.getByLabelText(/first name/i), { target: { value: values.firstName } });
    fireEvent.change(screen.getByLabelText(/last name/i), { target: { value: values.lastName } });
    fireEvent.change(screen.getByLabelText(/^email$/i), { target: { value: values.email } });
    // Password fields wrap a hint + show/hide button inside the label, so
    // the label's accessible name is polluted.  Target by id directly.
    fireEvent.change(document.getElementById("signup-password") as HTMLElement, {
      target: { value: values.password },
    });
    fireEvent.change(document.getElementById("signup-confirm") as HTMLElement, {
      target: { value: values.confirm },
    });
  }

  it("renders every required field and a Create account submit", () => {
    renderPage();
    expect(screen.getByLabelText(/first name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/last name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^email$/i)).toBeInTheDocument();
    expect(document.getElementById("signup-password")).toBeInTheDocument();
    expect(document.getElementById("signup-confirm")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create account/i })).toBeInTheDocument();
  });

  it("blocks submission when required fields are missing", async () => {
    amplifySignUp.mockResolvedValue({ nextStep: { signUpStep: "CONFIRM_SIGN_UP" } });
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/fill in all fields/i),
    );
    expect(amplifySignUp).not.toHaveBeenCalled();
  });

  it("blocks submission when password and confirmation differ", () => {
    renderPage();
    fillValid({ confirm: "Different-1!X" });
    // The submit button is disabled while passwords differ.
    expect(screen.getByRole("button", { name: /create account/i })).toBeDisabled();
    expect(screen.getByText(/passwords do not match yet/i)).toBeInTheDocument();
  });

  it("calls Amplify signUp with normalized email and Cognito standard attributes", async () => {
    amplifySignUp.mockResolvedValue({ nextStep: { signUpStep: "CONFIRM_SIGN_UP" } });
    renderPage();
    fillValid({ email: " Ada@Example.com " });
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));
    await waitFor(() => expect(amplifySignUp).toHaveBeenCalledTimes(1));
    expect(amplifySignUp).toHaveBeenCalledWith({
      username: "ada@example.com",
      password: "Correct-Horse-1!",
      options: {
        userAttributes: {
          email: "ada@example.com",
          given_name: "Ada",
          family_name: "Lovelace",
        },
      },
    });
  });

  it("routes to /verify-email with the email prefilled on CONFIRM_SIGN_UP", async () => {
    amplifySignUp.mockResolvedValue({ nextStep: { signUpStep: "CONFIRM_SIGN_UP" } });
    renderPage();
    fillValid();
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith(
        "/verify-email?email=ada%40example.com",
        { replace: true },
      ),
    );
  });

  it("routes straight to /login when Cognito returns nextStep DONE (auto-confirmed)", async () => {
    amplifySignUp.mockResolvedValue({ nextStep: { signUpStep: "DONE" } });
    renderPage();
    fillValid();
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/login", { replace: true }));
  });

  it("shows a policy-hint message when Cognito rejects the password", async () => {
    amplifySignUp.mockRejectedValue(
      Object.assign(new Error("policy detail"), { name: "InvalidPasswordException" }),
    );
    renderPage();
    fillValid();
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));
    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert).toHaveTextContent(/12 characters/);
      expect(alert).not.toHaveTextContent(/policy detail/);
    });
  });

  it("does not confirm account existence on UsernameExistsException", async () => {
    amplifySignUp.mockRejectedValue(
      Object.assign(new Error("account existed"), { name: "UsernameExistsException" }),
    );
    renderPage();
    fillValid();
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));
    await waitFor(() => {
      const alert = screen.getByRole("alert");
      // Enumeration-safe wording: the mapper's detail speaks of a 6-digit
      // verification code being sent, without confirming or denying that
      // the address is already registered.
      expect(alert).toHaveTextContent(/6-digit verification code/i);
      expect(alert).not.toHaveTextContent(/already/i);
    });
  });
});
