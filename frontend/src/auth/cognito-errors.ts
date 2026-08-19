// Map raw Amplify/Cognito errors to short, user-friendly strings the auth
// pages can render safely.
//
// The mapping deliberately avoids echoing back exception messages verbatim
// because:
//   1. AWS SDK stacks leak implementation details users cannot act on,
//   2. Some Cognito errors would enable account enumeration if surfaced
//      verbatim (e.g. "UserNotFoundException" vs "NotAuthorizedException").
//
// PreventUserExistenceErrors is already ENABLED on the app client, so
// Cognito returns the generic NotAuthorizedException for both wrong password
// and unknown email during sign-in.  This helper mirrors that stance and
// extends it to sign-up / verification / recovery flows where PR B needs
// friendly messages without leaking account existence.

export type AuthErrorMessage = {
  headline: string;
  detail?: string;
};

// The three contexts each have slightly different account-enumeration
// tradeoffs, so friendlyAuthError takes an optional `context` argument.
// Defaulting to "signin" preserves PR A's behaviour.
export type AuthErrorContext = "signin" | "signup" | "verify" | "recovery";

export function friendlyAuthError(
  err: unknown,
  context: AuthErrorContext = "signin",
): AuthErrorMessage {
  const name = (err as { name?: string } | null)?.name ?? "";
  // Surface the exception *name* (a constant class identifier, never a
  // secret, token, password, or user input) so failures are diagnosable
  // from the browser console instead of vanishing behind a friendly string.
  if (name) {
    console.warn(`[auth:${context}] ${name}`);
  } else {
    console.warn(`[auth:${context}] unrecognised error`, err);
  }
  switch (name) {
    // ---- shared ----------------------------------------------------------
    case "NotAuthorizedException":
    case "UserNotFoundException":
      if (context === "recovery") {
        // Account-enumeration-safe wording for password recovery: never
        // reveal whether the address is known.
        return {
          headline: "Check your email",
          detail:
            "If an account matches that email, we've sent recovery instructions. Please check your inbox.",
        };
      }
      return {
        headline: context === "signin" ? "Sign in failed" : "Request failed",
        detail: "The email or password you entered is incorrect.",
      };
    case "TooManyRequestsException":
    case "LimitExceededException":
      return {
        headline: "Too many attempts",
        detail: "Please wait a minute before trying again.",
      };
    case "TooManyFailedAttemptsException":
      return {
        headline: "Too many failed attempts",
        detail:
          "The account has been temporarily locked. Please try again in a few minutes.",
      };
    case "NetworkError":
    case "TypeError":
      return {
        headline: "Network error",
        detail:
          "SmartRetailX could not reach the authentication service. Check your connection and try again.",
      };
    case "InvalidParameterException":
      return {
        headline: "Invalid input",
        detail:
          "One of the fields did not meet the required format. Please check and try again.",
      };
    // ---- sign-in specific ----------------------------------------------
    case "UserNotConfirmedException":
      return {
        headline: "Account not confirmed",
        detail:
          "Your account still needs to be verified. Use the Verify account link below to enter the 6-digit code from your email.",
      };
    case "PasswordResetRequiredException":
      return {
        headline: "Password reset required",
        detail: "You need to reset your password before signing in.",
      };
    case "UserAlreadyAuthenticatedException":
      // Amplify v6 throws this when signIn is called while a session already
      // exists in storage.  The AuthContext now signs out and retries
      // automatically, so a user should rarely see this — but map it to a
      // clear, actionable message rather than the generic fallback.
      return {
        headline: "Already signed in",
        detail:
          "A previous session is still active. Please refresh the page, or sign out, then try again.",
      };
    case "EmptySignInUsername":
    case "EmptySignInPassword":
      return {
        headline: "Missing details",
        detail: "Please enter both your email and password.",
      };
    // ---- sign-up specific ----------------------------------------------
    case "UsernameExistsException":
      // Deliberately generic - do not confirm the address is registered.
      return {
        headline: "Check your email",
        detail:
          "If we could create an account for you, we've sent a 6-digit verification code to that address.",
      };
    case "InvalidPasswordException":
      return {
        headline: "Password does not meet the policy",
        detail:
          "Please use at least 12 characters including upper, lower, digit, and symbol.",
      };
    // ---- verification specific ------------------------------------------
    case "CodeMismatchException":
      return {
        headline: "Incorrect code",
        detail: "The verification code you entered is not valid. Please try again.",
      };
    case "ExpiredCodeException":
      return {
        headline: "Code expired",
        detail: "That code has expired. Please request a new one.",
      };
    case "AliasExistsException":
      return {
        headline: "Email already in use",
        detail: "That email address is already linked to a confirmed account.",
      };
    // ---- fallback --------------------------------------------------------
    default:
      return {
        headline: context === "signin" ? "Sign in failed" : "Something went wrong",
        detail: "Please try again in a moment.",
      };
  }
}
