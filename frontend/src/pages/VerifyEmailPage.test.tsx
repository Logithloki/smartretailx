import { describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { VerifyEmailPage } from "./VerifyEmailPage";

const navigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigate };
});

const confirmSignUpMock = vi.fn();
const resendCodeMock = vi.fn();
vi.mock("aws-amplify/auth", () => ({
  confirmSignUp: (args: unknown) => confirmSignUpMock(args),
  resendSignUpCode: (args: unknown) => resendCodeMock(args),
}));

function renderPage(url = "/verify-email?email=ada%40example.com") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <VerifyEmailPage />
    </MemoryRouter>,
  );
}

describe("VerifyEmailPage", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("prefills the email from the ?email query", () => {
    renderPage();
    expect(screen.getByLabelText(/^email$/i)).toHaveValue("ada@example.com");
  });

  it("strips non-digits from the verification code input", () => {
    renderPage();
    const input = screen.getByLabelText(/6-digit verification code/i);
    fireEvent.change(input, { target: { value: " 12abc3 " } });
    expect(input).toHaveValue("123");
  });

  it("submits a normalized username + trimmed code, then routes to /login", async () => {
    confirmSignUpMock.mockResolvedValue({ isSignUpComplete: true });
    renderPage();
    fireEvent.change(screen.getByLabelText(/6-digit verification code/i), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: /confirm account/i }));
    await waitFor(() => expect(confirmSignUpMock).toHaveBeenCalledTimes(1));
    expect(confirmSignUpMock).toHaveBeenCalledWith({
      username: "ada@example.com",
      confirmationCode: "123456",
    });
    expect(screen.getByRole("status")).toHaveTextContent(/redirecting/i);
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/login", { replace: true }), {
      timeout: 3000,
    });
  });

  it("shows the CodeMismatch message on wrong code", async () => {
    confirmSignUpMock.mockRejectedValue(
      Object.assign(new Error(""), { name: "CodeMismatchException" }),
    );
    renderPage();
    fireEvent.change(screen.getByLabelText(/6-digit verification code/i), {
      target: { value: "999999" },
    });
    fireEvent.click(screen.getByRole("button", { name: /confirm account/i }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/not valid/i),
    );
  });

  it("shows the expired-code message on ExpiredCodeException", async () => {
    confirmSignUpMock.mockRejectedValue(
      Object.assign(new Error(""), { name: "ExpiredCodeException" }),
    );
    renderPage();
    fireEvent.change(screen.getByLabelText(/6-digit verification code/i), {
      target: { value: "111111" },
    });
    fireEvent.click(screen.getByRole("button", { name: /confirm account/i }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/expired/i),
    );
  });

  it("resends a code with a safe generic message and enters a cooldown state", async () => {
    resendCodeMock.mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /^resend code$/i }));
    await waitFor(() => expect(resendCodeMock).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("status")).toHaveTextContent(/if the account exists/i);
    // The button becomes disabled and shows a countdown; the exact seconds
    // are timer-dependent, so just assert the disabled + "s)" affordance.
    const resendBtn = await screen.findByRole("button", { name: /Resend code \(\d+s\)/ });
    expect(resendBtn).toBeDisabled();
  });
});
