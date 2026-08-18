import { describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ForgotPasswordPage } from "./ForgotPasswordPage";

const navigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigate };
});

const resetPasswordMock = vi.fn();
vi.mock("aws-amplify/auth", () => ({
  resetPassword: (args: unknown) => resetPasswordMock(args),
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <ForgotPasswordPage />
    </MemoryRouter>,
  );
}

describe("ForgotPasswordPage", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("requires an email before calling Cognito", async () => {
    resetPasswordMock.mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /send recovery code/i }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/enter your email/i),
    );
    expect(resetPasswordMock).not.toHaveBeenCalled();
  });

  it("normalizes and calls resetPassword then routes to /reset-password", async () => {
    resetPasswordMock.mockResolvedValue(undefined);
    renderPage();
    fireEvent.change(screen.getByLabelText(/^email$/i), {
      target: { value: " Ada@Example.com " },
    });
    fireEvent.click(screen.getByRole("button", { name: /send recovery code/i }));
    await waitFor(() => expect(resetPasswordMock).toHaveBeenCalledTimes(1));
    expect(resetPasswordMock).toHaveBeenCalledWith({ username: "ada@example.com" });
    expect(navigate).toHaveBeenCalledWith(
      "/reset-password?email=ada%40example.com&sent=1",
      { replace: true },
    );
  });

  it("still routes to /reset-password when Cognito throws (account-enumeration safe)", async () => {
    resetPasswordMock.mockRejectedValue(
      Object.assign(new Error("cognito internal"), { name: "UserNotFoundException" }),
    );
    renderPage();
    fireEvent.change(screen.getByLabelText(/^email$/i), {
      target: { value: "unknown@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send recovery code/i }));
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith(
        "/reset-password?email=unknown%40example.com&sent=1",
        { replace: true },
      ),
    );
    // The user must NOT see the raw exception name.
    expect(screen.queryByText(/UserNotFoundException/)).toBeNull();
  });
});
