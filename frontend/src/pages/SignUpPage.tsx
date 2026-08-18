import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { signUp } from "aws-amplify/auth";
import { friendlyAuthError } from "../auth/cognito-errors";

// First-party SmartRetailX sign-up page.
//
// Cognito remains authoritative for password-policy enforcement; the
// helper text below is guidance only, and Cognito's response is final.
// The password is passed directly to Amplify (never to any SmartRetailX
// backend service), lives only transiently in component state during the
// interaction, and is never persisted, logged, or written to storage.
export function SignUpPage() {
  const navigate = useNavigate();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const passwordMismatch = confirm.length > 0 && password !== confirm;

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (submitting) return;
    setFormError(null);
    if (!firstName.trim() || !lastName.trim() || !email.trim() || !password) {
      setFormError("Please fill in all fields.");
      return;
    }
    if (password !== confirm) {
      setFormError("Password and confirmation do not match.");
      return;
    }
    setSubmitting(true);
    try {
      const normalisedEmail = email.trim().toLowerCase();
      const result = await signUp({
        username: normalisedEmail,
        password,
        options: {
          userAttributes: {
            email: normalisedEmail,
            given_name: firstName.trim(),
            family_name: lastName.trim(),
          },
        },
      });
      // Amplify returns nextStep.signUpStep = "CONFIRM_SIGN_UP" for the
      // normal case where Cognito emailed a 6-digit code.  If the pool
      // auto-confirmed the user (never happens for real users after PR B's
      // Test Lambda narrowing) the step is "DONE" and we send them to Sign
      // In directly.
      if (result.nextStep.signUpStep === "DONE") {
        navigate("/login", { replace: true });
      } else {
        navigate(`/verify-email?email=${encodeURIComponent(normalisedEmail)}`, {
          replace: true,
        });
      }
    } catch (err) {
      const mapped = friendlyAuthError(err, "signup");
      setFormError(mapped.detail ?? mapped.headline);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page-container">
      <div className="auth-card">
        <div className="auth-card-header">
          <h1>SmartRetailX</h1>
          <p>Create your account</p>
        </div>

        {formError && (
          <div className="alert-error" role="alert">
            {formError}
          </div>
        )}

        <form onSubmit={submit} noValidate>
          <label htmlFor="signup-first-name">
            First name
            <input
              id="signup-first-name"
              name="given_name"
              type="text"
              autoComplete="given-name"
              value={firstName}
              onChange={(event) => setFirstName(event.target.value)}
              disabled={submitting}
              required
            />
          </label>

          <label htmlFor="signup-last-name">
            Last name
            <input
              id="signup-last-name"
              name="family_name"
              type="text"
              autoComplete="family-name"
              value={lastName}
              onChange={(event) => setLastName(event.target.value)}
              disabled={submitting}
              required
            />
          </label>

          <label htmlFor="signup-email">
            Email
            <input
              id="signup-email"
              name="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              disabled={submitting}
              required
            />
          </label>

          <label htmlFor="signup-password">
            Password
            <div className="password-input-wrap">
              <input
                id="signup-password"
                name="new-password"
                type={showPassword ? "text" : "password"}
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                disabled={submitting}
                required
                aria-describedby="signup-password-guidance"
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
            <div id="signup-password-guidance" className="auth-hint">
              At least 12 characters with upper, lower, digit, and symbol.
              Cognito enforces the final policy.
            </div>
          </label>

          <label htmlFor="signup-confirm">
            Confirm password
            <input
              id="signup-confirm"
              name="confirm-password"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              disabled={submitting}
              required
              aria-invalid={passwordMismatch}
            />
            {passwordMismatch && (
              <div className="auth-hint auth-hint-error" role="status">
                Passwords do not match yet.
              </div>
            )}
          </label>

          <button
            type="submit"
            className="auth-submit-btn"
            disabled={submitting || passwordMismatch}
          >
            {submitting ? "Creating account…" : "Create account"}
          </button>
        </form>

        <div className="auth-links">
          <Link to="/login">Back to Sign in</Link>
        </div>
      </div>
    </div>
  );
}
