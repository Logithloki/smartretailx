import { describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ResetPasswordPage } from "./ResetPasswordPage";

const navigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigate };
});

const confirmResetPasswordMock = vi.fn();
vi.mock("aws-amplify/auth", () => ({
  confirmResetPassword: (args: unknown) => confirmResetPasswordMock(args),
}));

function renderPage(url = "/reset-password?email=ada%40example.com&sent=1") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <ResetPasswordPage />
    </MemoryRouter>,
  );
}

describe("ResetPasswordPage", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  function fillValid(overrides: Partial<Record<string, string>> = {}): void {
    const values = {
      code: "123456",
      password: "Correct-Horse-9!Z",
      confirm: "Correct-Horse-9!Z",
      ...overrides,
    };
    fireEvent.change(screen.getByLabelText(/6-digit recovery code/i), {
      target: { value: values.code },
    });
    // Password fields wrap a hint + show/hide button inside the label,
    // polluting the accessible name.  Target by id directly.
    fireEvent.change(document.getElementById("reset-password") as HTMLElement, {
      target: { value: values.password },
    });
    fireEvent.change(document.getElementById("reset-confirm") as HTMLElement, {
      target: { value: values.confirm },
    });
  }

  it("prefills email + shows the account-safe sent banner when ?sent=1", () => {
    renderPage();
    expect(screen.getByLabelText(/^email$/i)).toHaveValue("ada@example.com");
    expect(screen.getByRole("status")).toHaveTextContent(/if an account matches/i);
  });

  it("disables submit while password + confirmation differ", () => {
    renderPage();
    fillValid({ confirm: "Different-1!X" });
    expect(screen.getByRole("button", { name: /set new password/i })).toBeDisabled();
  });

  it("calls confirmResetPassword with normalized args and routes to /login on success", async () => {
    confirmResetPasswordMock.mockResolvedValue(undefined);
    renderPage();
    fillValid();
    fireEvent.click(screen.getByRole("button", { name: /set new password/i }));
    await waitFor(() => expect(confirmResetPasswordMock).toHaveBeenCalledTimes(1));
    expect(confirmResetPasswordMock).toHaveBeenCalledWith({
      username: "ada@example.com",
      confirmationCode: "123456",
      newPassword: "Correct-Horse-9!Z",
    });
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/login", { replace: true }), {
      timeout: 3000,
    });
  });

  it("maps CodeMismatch, ExpiredCode, and InvalidPassword to friendly text", async () => {
    for (const { name, expected } of [
      { name: "CodeMismatchException", expected: /not valid/i },
      { name: "ExpiredCodeException", expected: /expired/i },
      { name: "InvalidPasswordException", expected: /12 characters/i },
    ]) {
      cleanup();
      vi.clearAllMocks();
      confirmResetPasswordMock.mockRejectedValue(Object.assign(new Error(""), { name }));
      renderPage();
      fillValid();
      fireEvent.click(screen.getByRole("button", { name: /set new password/i }));
      await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(expected));
    }
  });
});
