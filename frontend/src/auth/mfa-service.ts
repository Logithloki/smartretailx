// Thin, testable wrappers around Amplify Auth v6's TOTP MFA APIs.
//
// Every MFA-related interaction with Cognito must go through this module
// so tests can stub a single seam and so we can enforce a couple of
// SmartRetailX-specific safety rules:
//
//   * The TOTP shared secret returned by Cognito is passed to the caller
//     but never stored here, never logged, and never sent to any
//     SmartRetailX-owned backend service.  Callers must clear their own
//     copy of the secret once enrolment succeeds.
//
//   * The MFA "enabled" state is not cached in application storage.  It
//     is always resolved from Cognito via fetchMFAPreference so the UI
//     cannot drift out of sync with the authoritative state.
//
//   * A UI-only guard prevents accidental enrolment on dedicated CI
//     automation identities.  This is NOT a security boundary - it only
//     protects an admin from clicking Enable on a CI account by mistake
//     while signed in as that CI user.  Cognito remains the authority.
import {
  confirmSignIn,
  fetchMFAPreference,
  setUpTOTP,
  updateMFAPreference,
  verifyTOTPSetup,
} from "aws-amplify/auth";
import type { FetchMFAPreferenceOutput } from "aws-amplify/auth";
type TOTPSetupDetails = Awaited<ReturnType<typeof setUpTOTP>>;

// Exact CI/E2E identity pattern from the Cognito pre-signup Lambda (PR B).
// Keep the two in sync if either changes.
export const CI_IDENTITY_PATTERN =
  /^ci-(smoke|customer|admin)-(development|test|staging)@example\.com$/;

export function isCiAutomationEmail(email: string | null | undefined): boolean {
  if (!email) return false;
  return CI_IDENTITY_PATTERN.test(email.trim().toLowerCase());
}

export interface MfaStatus {
  enabled: boolean;
  preferred: FetchMFAPreferenceOutput["preferred"];
  raw: FetchMFAPreferenceOutput;
}

export async function loadMfaStatus(): Promise<MfaStatus> {
  const preference = await fetchMFAPreference();
  const enabled = Boolean(
    preference.enabled?.includes("TOTP") || preference.preferred === "TOTP",
  );
  return { enabled, preferred: preference.preferred, raw: preference };
}

export interface TotpSetup {
  sharedSecret: string;
  setupUri: string;
}

// Returns the shared secret + otpauth:// URI the UI needs to render a QR.
// The caller MUST clear both from its state once verifyAndActivate succeeds.
export async function beginTotpSetup(
  accountName: string,
  issuer = "SmartRetailX",
): Promise<TotpSetup> {
  const details: TOTPSetupDetails = await setUpTOTP();
  const uri = details.getSetupUri(issuer, accountName).toString();
  return { sharedSecret: details.sharedSecret, setupUri: uri };
}

// Verify the current 6-digit TOTP from the user's authenticator, then flip
// their MFA preference to TOTP so future sign-ins are challenged.
export async function verifyAndActivateTotp(code: string): Promise<void> {
  await verifyTOTPSetup({ code });
  await updateMFAPreference({ totp: "PREFERRED" });
}

export async function disableTotp(): Promise<void> {
  await updateMFAPreference({ totp: "DISABLED" });
}

// Complete a Cognito TOTP challenge issued during sign-in.  Amplify holds
// the pending session in memory after signIn(); confirmSignIn resumes it.
export async function submitTotpChallenge(code: string): Promise<void> {
  await confirmSignIn({ challengeResponse: code });
}
