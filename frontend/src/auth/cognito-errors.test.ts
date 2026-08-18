import { describe, expect, it } from "vitest";
import { friendlyAuthError } from "./cognito-errors";

describe("friendlyAuthError", () => {
  it("returns a generic message for wrong password / unknown user (PreventUserExistenceErrors)", () => {
    for (const name of ["NotAuthorizedException", "UserNotFoundException"]) {
      const err = Object.assign(new Error("cognito internal detail"), { name });
      const mapped = friendlyAuthError(err);
      expect(mapped.headline).toBe("Sign in failed");
      expect(mapped.detail).toMatch(/email or password.*incorrect/i);
      // The raw exception text must never leak.
      expect(mapped.detail).not.toMatch(/internal detail/);
    }
  });

  it("directs unconfirmed accounts to check email", () => {
    const err = Object.assign(new Error("nope"), { name: "UserNotConfirmedException" });
    const mapped = friendlyAuthError(err);
    expect(mapped.headline).toBe("Account not confirmed");
    expect(mapped.detail).toMatch(/verification email/i);
  });

  it("recognises PasswordResetRequiredException", () => {
    const err = Object.assign(new Error(""), { name: "PasswordResetRequiredException" });
    expect(friendlyAuthError(err).headline).toBe("Password reset required");
  });

  it("recognises rate limiting", () => {
    for (const name of ["TooManyRequestsException", "LimitExceededException"]) {
      const err = Object.assign(new Error(""), { name });
      expect(friendlyAuthError(err).headline).toBe("Too many attempts");
    }
  });

  it("distinguishes network failure from generic error", () => {
    for (const name of ["NetworkError", "TypeError"]) {
      const err = Object.assign(new Error(""), { name });
      expect(friendlyAuthError(err).headline).toBe("Network error");
    }
  });

  it("returns a generic fallback for unknown Cognito errors", () => {
    const err = Object.assign(new Error("brand new exception"), { name: "UnheardOfException" });
    const mapped = friendlyAuthError(err);
    expect(mapped.headline).toBe("Sign in failed");
    expect(mapped.detail).not.toMatch(/brand new exception/);
  });

  it("returns a generic fallback for a non-Error value", () => {
    expect(friendlyAuthError(null).headline).toBe("Sign in failed");
    expect(friendlyAuthError("string").headline).toBe("Sign in failed");
  });
});
