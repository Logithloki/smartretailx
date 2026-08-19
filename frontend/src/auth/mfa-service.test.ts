import { describe, expect, it, vi, beforeEach } from "vitest";

const setUpTOTPMock = vi.fn();
const verifyTOTPSetupMock = vi.fn();
const updateMFAPreferenceMock = vi.fn();
const fetchMFAPreferenceMock = vi.fn();
const confirmSignInMock = vi.fn();

vi.mock("aws-amplify/auth", () => ({
  setUpTOTP: () => setUpTOTPMock(),
  verifyTOTPSetup: (args: unknown) => verifyTOTPSetupMock(args),
  updateMFAPreference: (args: unknown) => updateMFAPreferenceMock(args),
  fetchMFAPreference: () => fetchMFAPreferenceMock(),
  confirmSignIn: (args: unknown) => confirmSignInMock(args),
}));

import {
  beginTotpSetup,
  disableTotp,
  isCiAutomationEmail,
  loadMfaStatus,
  submitTotpChallenge,
  verifyAndActivateTotp,
} from "./mfa-service";

describe("isCiAutomationEmail", () => {
  it("matches exactly the runtime-mint synthetic CI identities", () => {
    for (const email of [
      "ci-smoke-development@example.com",
      "ci-customer-test@example.com",
      "ci-admin-staging@example.com",
    ]) {
      expect(isCiAutomationEmail(email)).toBe(true);
      // Case-insensitive on the address side.
      expect(isCiAutomationEmail(email.toUpperCase())).toBe(true);
      expect(isCiAutomationEmail(` ${email} `)).toBe(true);
    }
  });

  it("does NOT match adjacent-looking real addresses", () => {
    for (const email of [
      "ci-smoke-production@example.com", // production is not in the CI env set
      "ci-admin-@example.com",
      "smoke-ci-test@example.com",
      "ci-smoke-test@evil.com",
      "customer@example.com",
      "ada@smartretailx.com",
      "",
      null,
      undefined,
    ]) {
      expect(isCiAutomationEmail(email as string)).toBe(false);
    }
  });
});

describe("MFA service wrappers", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loadMfaStatus reports enabled=true when TOTP is in enabled list", async () => {
    fetchMFAPreferenceMock.mockResolvedValue({ enabled: ["TOTP"], preferred: "TOTP" });
    const status = await loadMfaStatus();
    expect(status.enabled).toBe(true);
    expect(status.preferred).toBe("TOTP");
  });

  it("loadMfaStatus reports enabled=false when nothing is enrolled", async () => {
    fetchMFAPreferenceMock.mockResolvedValue({ enabled: [], preferred: undefined });
    const status = await loadMfaStatus();
    expect(status.enabled).toBe(false);
  });

  it("beginTotpSetup returns the shared secret and constructs an otpauth setup URI", async () => {
    setUpTOTPMock.mockResolvedValue({
      sharedSecret: "SHARED-SECRET-SYNTHETIC",
      getSetupUri: (issuer: string, account: string) => new URL(
        `otpauth://totp/${encodeURIComponent(issuer)}:${encodeURIComponent(account)}?secret=SHARED-SECRET-SYNTHETIC&issuer=${encodeURIComponent(issuer)}`,
      ),
    });
    const setup = await beginTotpSetup("ada@example.com");
    expect(setup.sharedSecret).toBe("SHARED-SECRET-SYNTHETIC");
    expect(setup.setupUri).toContain("otpauth://totp/");
    expect(setup.setupUri).toContain("issuer=SmartRetailX");
    expect(setup.setupUri).toContain("ada%40example.com");
  });

  it("verifyAndActivateTotp verifies then flips preference to PREFERRED", async () => {
    verifyTOTPSetupMock.mockResolvedValue(undefined);
    updateMFAPreferenceMock.mockResolvedValue(undefined);
    await verifyAndActivateTotp("123456");
    expect(verifyTOTPSetupMock).toHaveBeenCalledWith({ code: "123456" });
    expect(updateMFAPreferenceMock).toHaveBeenCalledWith({ totp: "PREFERRED" });
  });

  it("verifyAndActivateTotp does NOT flip preference if verify fails", async () => {
    verifyTOTPSetupMock.mockRejectedValue(
      Object.assign(new Error(""), { name: "CodeMismatchException" }),
    );
    await expect(verifyAndActivateTotp("999999")).rejects.toBeDefined();
    expect(updateMFAPreferenceMock).not.toHaveBeenCalled();
  });

  it("disableTotp sets preference to DISABLED", async () => {
    updateMFAPreferenceMock.mockResolvedValue(undefined);
    await disableTotp();
    expect(updateMFAPreferenceMock).toHaveBeenCalledWith({ totp: "DISABLED" });
  });

  it("submitTotpChallenge forwards the code to confirmSignIn", async () => {
    confirmSignInMock.mockResolvedValue(undefined);
    await submitTotpChallenge("654321");
    expect(confirmSignInMock).toHaveBeenCalledWith({ challengeResponse: "654321" });
  });
});
