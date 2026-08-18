import { FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useAuth } from "../context/useAuth";
import { friendlyAuthError } from "../auth/cognito-errors";
import { createAuthConfig } from "../auth-config";
import { getRuntimeConfig } from "../config/runtime-config";
import { UserManager } from "oidc-client-ts";

// Custom SmartRetailX sign-in page.
//
// Users enter their credentials directly here; the auth context relays them
// to Cognito over SRP (Secure Remote Password) — the password is never
// transmitted in cleartext and never touches any SmartRetailX-owned service.
//
// Cognito Hosted UI remains available as an emergency rollback if the new
// path develops a defect: visit `/login?fallback=hosted-ui` and click the
// button that appears.  It is not offered to normal users.
export function SignInPage() {
  const auth = useAuth();
  const [searchParams] = useSearchParams();
  const hostedUiFallback = searchParams.get("fallback") === "hosted-ui";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [challengeMessage, setChallengeMessage] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (submitting) return;
    setFormError(null);
    setChallengeMessage(null);
    if (!email.trim() || !password) {
      setFormError("Please enter both your email and password.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await auth.signIn(email, password);
      if (!result.isSignedIn) {
        // The auth context has already recorded the challenge state.  PR C
        // will add dedicated UX for each; for PR A we surface a short,
        // implementation-detail-free message so users are not left staring
        // at a blank screen.
        switch (result.nextStep.signInStep) {
          case "CONFIRM_SIGN_IN_WITH_TOTP_CODE":
          case "CONFIRM_SIGN_IN_WITH_SMS_CODE":
          case "CONFIRM_SIGN_IN_WITH_EMAIL_CODE":
            setChallengeMessage(
              "Multi-factor authentication is required for this account. The verification screen will land in the next SmartRetailX release; please contact an administrator if you are locked out.",
            );
            break;
          case "CONTINUE_SIGN_IN_WITH_TOTP_SETUP":
            setChallengeMessage(
              "Multi-factor authentication setup is required for this account. The setup screen will land in the next SmartRetailX release.",
            );
            break;
          case "CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED":
            setChallengeMessage(
              "This account must set a new password before continuing. The password-change screen will land in the next SmartRetailX release; please contact an administrator.",
            );
            break;
          default:
            setChallengeMessage(
              "This account requires an additional authentication step that SmartRetailX cannot yet complete.",
            );
        }
      }
    } catch (err) {
      const mapped = friendlyAuthError(err);
      setFormError(mapped.detail ?? mapped.headline);
    } finally {
      setSubmitting(false);
    }
  }

  async function beginHostedUiFallback(): Promise<void> {
    // Emergency rollback path.  Constructs a UserManager on demand and
    // triggers the Hosted UI code+PKCE flow.
    const manager = new UserManager(createAuthConfig(getRuntimeConfig()));
    await manager.signinRedirect();
  }

  return (
    <div className="auth-page-container">
      <div className="auth-card">
        <div className="auth-card-header">
          <h1>SmartRetailX</h1>
          <p>Sign in to your account</p>
        </div>

        {(auth.error || formError) && (
          <div className="alert-error" role="alert">
            {formError ?? auth.error?.message}
          </div>
        )}

        {challengeMessage && (
          <div className="alert-error" role="status">
            {challengeMessage}
          </div>
        )}

        <form onSubmit={submit} noValidate>
          <label htmlFor="signin-email">
            Email
            <input
              id="signin-email"
              name="email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              disabled={submitting}
              required
            />
          </label>

          <label htmlFor="signin-password">
            Password
            <div className="password-input-wrap">
              <input
                id="signin-password"
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                disabled={submitting}
                required
              />
              <button
                type="button"
                className="password-visibility-toggle"
                aria-pressed={showPassword}
                aria-label={showPassword ? "Hide password" : "Show password"}
                onClick={() => setShowPassword((v) => !v)}
                disabled={submitting}
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
          </label>

          <button
            type="submit"
            className="auth-submit-btn"
            disabled={submitting}
          >
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="auth-links">
          <Link to="/forgot-password" aria-disabled="true" className="disabled-link" title="Coming in the next SmartRetailX release">
            Forgot password?
          </Link>
          <Link to="/signup" aria-disabled="true" className="disabled-link" title="Coming in the next SmartRetailX release">
            Create account
          </Link>
        </div>

        <div className="auth-footer-note">
          Cognito · SRP · session managed by AWS Amplify Auth v6
        </div>

        {hostedUiFallback && (
          <div className="auth-fallback">
            <p className="auth-fallback-notice">
              Hosted UI fallback (rollback path). Do not use unless the custom sign-in above is broken.
            </p>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void beginHostedUiFallback()}
            >
              Continue with Hosted UI
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
