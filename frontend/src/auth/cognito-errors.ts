// Map raw Amplify/Cognito errors to short, user-friendly strings the SignIn
// page (and later, other auth pages) can render safely.
//
// The mapping deliberately avoids echoing back exception messages verbatim
// because:
//   1. AWS SDK stacks leak implementation details users cannot act on,
//   2. Some Cognito errors would enable account enumeration if surfaced
//      verbatim (e.g. "UserNotFoundException" vs "NotAuthorizedException").
//
// PreventUserExistenceErrors is already ENABLED on the app client, so
// Cognito returns the generic NotAuthorizedException for both wrong password
// and unknown email.  This helper mirrors that stance.

export type AuthErrorMessage = {
  headline: string;
  detail?: string;
};

// Amplify surfaces error names on the underlying Error.  When available we
// pattern-match on the name; otherwise we fall through to a generic message.
export function friendlyAuthError(err: unknown): AuthErrorMessage {
  const name = (err as { name?: string } | null)?.name ?? "";
  switch (name) {
    case "NotAuthorizedException":
    case "UserNotFoundException":
      return {
        headline: "Sign in failed",
        detail: "The email or password you entered is incorrect.",
      };
    case "UserNotConfirmedException":
      return {
        headline: "Account not confirmed",
        detail: "Please check your inbox for the verification email and confirm the account before signing in.",
      };
    case "PasswordResetRequiredException":
      return {
        headline: "Password reset required",
        detail: "You need to reset your password before signing in.",
      };
    case "TooManyRequestsException":
    case "LimitExceededException":
      return {
        headline: "Too many attempts",
        detail: "Please wait a minute before trying to sign in again.",
      };
    case "NetworkError":
    case "TypeError":
      return {
        headline: "Network error",
        detail: "SmartRetailX could not reach the authentication service. Check your connection and try again.",
      };
    case "InvalidParameterException":
    case "InvalidPasswordException":
      return {
        headline: "Invalid input",
        detail: "One of the fields did not meet the required format. Please check and try again.",
      };
    default:
      return {
        headline: "Sign in failed",
        detail: "Something went wrong signing you in. Please try again.",
      };
  }
}
