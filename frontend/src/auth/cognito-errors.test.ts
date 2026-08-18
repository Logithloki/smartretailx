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

  it("directs unconfirmed accounts to the verify-account UX", () => {
    const err = Object.assign(new Error("nope"), { name: "UserNotConfirmedException" });
    const mapped = friendlyAuthError(err);
    expect(mapped.headline).toBe("Account not confirmed");
    expect(mapped.detail).toMatch(/verify account/i);
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

  // ---- PR B extensions ----------------------------------------------

  it("returns an account-enumeration-safe message for recovery context", () => {
    for (const name of ["NotAuthorizedException", "UserNotFoundException"]) {
      const err = Object.assign(new Error("cognito"), { name });
      const mapped = friendlyAuthError(err, "recovery");
      expect(mapped.headline).toBe("Check your email");
      expect(mapped.detail).toMatch(/if an account matches/i);
    }
  });

  it("does not confirm account existence on UsernameExistsException", () => {
    const err = Object.assign(new Error(""), { name: "UsernameExistsException" });
    const mapped = friendlyAuthError(err, "signup");
    // The wording must be generic - "check your email" - not "already exists".
    expect(mapped.headline).toBe("Check your email");
    expect(mapped.detail?.toLowerCase()).not.toContain("already");
  });

  it("maps InvalidPasswordException to a policy-hint message on signup", () => {
    const err = Object.assign(new Error(""), { name: "InvalidPasswordException" });
    const mapped = friendlyAuthError(err, "signup");
    expect(mapped.headline).toMatch(/password.*policy/i);
    expect(mapped.detail).toMatch(/12 characters/);
  });

  it("maps CodeMismatch and ExpiredCode on verify", () => {
    const bad = Object.assign(new Error(""), { name: "CodeMismatchException" });
    expect(friendlyAuthError(bad, "verify").headline).toBe("Incorrect code");
    const stale = Object.assign(new Error(""), { name: "ExpiredCodeException" });
    expect(friendlyAuthError(stale, "verify").headline).toBe("Code expired");
  });

  it("maps AliasExistsException for verify to a clear message", () => {
    const err = Object.assign(new Error(""), { name: "AliasExistsException" });
    expect(friendlyAuthError(err, "verify").headline).toBe("Email already in use");
  });

  it("routes UserNotConfirmedException to a verify-account guidance", () => {
    const err = Object.assign(new Error(""), { name: "UserNotConfirmedException" });
    const mapped = friendlyAuthError(err);
    expect(mapped.headline).toBe("Account not confirmed");
    expect(mapped.detail).toMatch(/verify account/i);
  });

  it("maps TooManyFailedAttemptsException to a lockout message", () => {
    const err = Object.assign(new Error(""), { name: "TooManyFailedAttemptsException" });
    expect(friendlyAuthError(err).headline).toMatch(/failed attempts/i);
  });
});
