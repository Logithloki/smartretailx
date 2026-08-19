import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/useAuth";
import { submitTotpChallenge } from "../auth/mfa-service";
import { friendlyAuthError } from "../auth/cognito-errors";

// TOTP challenge screen shown after the sign-in password step when
// Cognito responds with CONFIRM_SIGN_IN_WITH_TOTP_CODE.  Amplify holds
// the pending session in memory after signIn(); confirmSignIn resumes
// it, so this page must be reached via react-router navigation (not a
// hard page reload) to keep that session alive.
export function MfaChallengePage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (submitting || code.length !== 6) return;
    setSubmitting(true);
    setError(null);
    try {
      await submitTotpChallenge(code);
      await auth.refreshFromCognito();
      navigate("/products", { replace: true });
    } catch (err) {
      const mapped = friendlyAuthError(err, "verify");
      setError(mapped.detail ?? mapped.headline);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page-container">
      <div className="auth-card">
        <div className="auth-card-header">
          <h1>SmartRetailX</h1>
          <p>Two-factor authentication</p>
        </div>

        {error && (
          <div className="alert-error" role="alert">
            {error}
          </div>
        )}

        <p>Enter the current 6-digit code from your authenticator app.</p>

        <form onSubmit={submit} noValidate>
          <label htmlFor="mfa-challenge-code">
            Authenticator code
          </label>
          <input
            id="mfa-challenge-code"
            name="code"
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            pattern="[0-9]{6}"
            autoFocus
            value={code}
            onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
            disabled={submitting}
            required
          />

          <button
            type="submit"
            className="auth-submit-btn"
            disabled={submitting || code.length !== 6}
          >
            {submitting ? "Verifying…" : "Verify"}
          </button>
        </form>

        <div className="auth-links">
          <Link to="/login" onClick={() => void auth.removeUser()}>
            Cancel and sign in as someone else
          </Link>
        </div>

        <div className="auth-footer-note">
          Cognito · TOTP · session managed by AWS Amplify Auth v6
        </div>
      </div>
    </div>
  );
}
