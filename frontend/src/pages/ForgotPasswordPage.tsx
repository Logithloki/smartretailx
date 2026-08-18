import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { resetPassword } from "aws-amplify/auth";
import { friendlyAuthError } from "../auth/cognito-errors";

// Account-enumeration-safe password recovery start.  We ALWAYS show the
// same "check your inbox" message, whether or not the address is known to
// Cognito, before routing to /reset-password.  Recovery-context errors
// are also mapped to the same generic wording.
export function ForgotPasswordPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (submitting) return;
    setFormError(null);
    const normalisedEmail = email.trim().toLowerCase();
    if (!normalisedEmail) {
      setFormError("Please enter your email.");
      return;
    }
    setSubmitting(true);
    try {
      // Attempt regardless of whether the address exists.  Cognito will
      // silently no-op for unknown addresses under our current pool
      // configuration; either way we route the user to the reset screen
      // with the same messaging.
      await resetPassword({ username: normalisedEmail }).catch(() => {
        /* Swallow enumeration-relevant errors; friendlyAuthError below
           handles the safe generic messages for anything else. */
      });
      navigate(
        `/reset-password?email=${encodeURIComponent(normalisedEmail)}&sent=1`,
        { replace: true },
      );
    } catch (err) {
      const mapped = friendlyAuthError(err, "recovery");
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
          <p>Recover your account</p>
        </div>

        {formError && (
          <div className="alert-error" role="alert">
            {formError}
          </div>
        )}

        <form onSubmit={submit} noValidate>
          <label htmlFor="forgot-email">
            Email
            <input
              id="forgot-email"
              name="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              disabled={submitting}
              required
            />
          </label>

          <button
            type="submit"
            className="auth-submit-btn"
            disabled={submitting}
          >
            {submitting ? "Requesting…" : "Send recovery code"}
          </button>
        </form>

        <div className="auth-links">
          <Link to="/login">Back to Sign in</Link>
        </div>

        <div className="auth-footer-note">
          If an account matches that email, we'll send a 6-digit recovery code.
        </div>
      </div>
    </div>
  );
}
