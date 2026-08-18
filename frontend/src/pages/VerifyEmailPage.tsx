import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { confirmSignUp, resendSignUpCode } from "aws-amplify/auth";
import { friendlyAuthError } from "../auth/cognito-errors";

// Cognito sends 6-digit verification codes.  The user pastes/enters the
// code here and we call confirmSignUp; on success we route them to Sign
// In.  Verification codes are never logged.
export function VerifyEmailPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const emailFromQuery = (searchParams.get("email") ?? "").trim();
  const [email, setEmail] = useState(emailFromQuery);
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (resendCooldown <= 0) return;
    const t = window.setTimeout(() => setResendCooldown((n) => n - 1), 1000);
    return () => window.clearTimeout(t);
  }, [resendCooldown]);

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (submitting) return;
    setFormError(null);
    setFormSuccess(null);
    if (!email.trim() || !code.trim()) {
      setFormError("Please enter both your email and the 6-digit code.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await confirmSignUp({
        username: email.trim().toLowerCase(),
        confirmationCode: code.trim(),
      });
      if (result.isSignUpComplete) {
        setFormSuccess("Account confirmed. Redirecting to sign in…");
        window.setTimeout(() => navigate("/login", { replace: true }), 1200);
      } else {
        setFormError("Additional steps are required. Please contact support.");
      }
    } catch (err) {
      const mapped = friendlyAuthError(err, "verify");
      setFormError(mapped.detail ?? mapped.headline);
    } finally {
      setSubmitting(false);
    }
  }

  async function resend(): Promise<void> {
    if (resending || resendCooldown > 0 || !email.trim()) return;
    setResending(true);
    setFormError(null);
    setFormSuccess(null);
    try {
      await resendSignUpCode({ username: email.trim().toLowerCase() });
      setFormSuccess("If the account exists, a new verification code has been sent.");
      setResendCooldown(30);
    } catch (err) {
      const mapped = friendlyAuthError(err, "verify");
      setFormError(mapped.detail ?? mapped.headline);
    } finally {
      setResending(false);
    }
  }

  return (
    <div className="auth-page-container">
      <div className="auth-card">
        <div className="auth-card-header">
          <h1>SmartRetailX</h1>
          <p>Verify your email</p>
        </div>

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
          <label htmlFor="verify-email">
            Email
            <input
              id="verify-email"
              name="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              disabled={submitting}
              required
            />
          </label>

          <label htmlFor="verify-code">
            6-digit verification code
            <input
              id="verify-code"
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

          <button
            type="submit"
            className="auth-submit-btn"
            disabled={submitting}
          >
            {submitting ? "Confirming…" : "Confirm account"}
          </button>
        </form>

        <div className="auth-links">
          <button
            type="button"
            className="linkish"
            onClick={() => void resend()}
            disabled={resending || resendCooldown > 0 || !email.trim()}
          >
            {resendCooldown > 0
              ? `Resend code (${resendCooldown}s)`
              : resending
                ? "Sending…"
                : "Resend code"}
          </button>
          <Link to="/login">Back to Sign in</Link>
        </div>
      </div>
    </div>
  );
}
