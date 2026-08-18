import { FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { confirmResetPassword } from "aws-amplify/auth";
import { friendlyAuthError } from "../auth/cognito-errors";

// Second half of the password recovery flow.  The user supplies the
// 6-digit code Cognito sent + their new password; on success we route
// them back to Sign In (we do NOT auto-sign-in - fewer surprises, and the
// user's fresh password is validated by an explicit sign-in step).
export function ResetPasswordPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const emailFromQuery = (searchParams.get("email") ?? "").trim();
  const sentBanner = searchParams.get("sent") === "1";
  const [email, setEmail] = useState(emailFromQuery);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);

  const passwordMismatch = confirm.length > 0 && password !== confirm;

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (submitting) return;
    setFormError(null);
    setFormSuccess(null);
    if (!email.trim() || !code.trim() || !password) {
      setFormError("Please fill in all fields.");
      return;
    }
    if (password !== confirm) {
      setFormError("Password and confirmation do not match.");
      return;
    }
    setSubmitting(true);
    try {
      await confirmResetPassword({
        username: email.trim().toLowerCase(),
        confirmationCode: code.trim(),
        newPassword: password,
      });
      setFormSuccess("Password reset successful. Redirecting to sign in…");
      window.setTimeout(() => navigate("/login", { replace: true }), 1500);
    } catch (err) {
      const mapped = friendlyAuthError(err, "verify");
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
          <p>Set a new password</p>
        </div>

        {sentBanner && !formError && !formSuccess && (
          <div className="alert-info" role="status">
            If an account matches that email, we've sent a 6-digit recovery
            code.
          </div>
        )}
        {formError && (
          <div className="alert-error" role="alert">
            {formError}
          </div>
        )}
        {formSuccess && (
          <div className="alert-success" role="status">
            {formSuccess}
          </div>
        )}

        <form onSubmit={submit} noValidate>
          <label htmlFor="reset-email">
            Email
            <input
              id="reset-email"
              name="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              disabled={submitting}
              required
            />
          </label>

          <label htmlFor="reset-code">
            6-digit recovery code
            <input
              id="reset-code"
              name="code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              pattern="[0-9]{6}"
              value={code}
              onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
              disabled={submitting}
              required
            />
          </label>

          <label htmlFor="reset-password">
            New password
            <div className="password-input-wrap">
              <input
                id="reset-password"
                name="new-password"
                type={showPassword ? "text" : "password"}
                autoComplete="new-password"
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
            <div className="auth-hint">
              At least 12 characters with upper, lower, digit, and symbol.
              Cognito enforces the final policy.
            </div>
          </label>

          <label htmlFor="reset-confirm">
            Confirm new password
            <input
              id="reset-confirm"
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
            {submitting ? "Saving…" : "Set new password"}
          </button>
        </form>

        <div className="auth-links">
          <Link to="/login">Back to Sign in</Link>
        </div>
      </div>
    </div>
  );
}
