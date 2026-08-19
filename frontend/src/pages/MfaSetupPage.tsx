import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import QRCode from "qrcode";
import { useAuth } from "../context/useAuth";
import {
  beginTotpSetup,
  verifyAndActivateTotp,
} from "../auth/mfa-service";
import { friendlyAuthError } from "../auth/cognito-errors";

// Two-step TOTP enrolment screen used from Security > Enable MFA and,
// when Cognito issues the CONTINUE_SIGN_IN_WITH_TOTP_SETUP challenge on
// sign-in, from the auth state machine.  A single implementation keeps
// the flow consistent regardless of how the user arrives here.
//
// The shared secret + otpauth URI are held ONLY in component state
// during enrolment.  Both are cleared on unmount, on cancel, and on
// successful verifyAndActivateTotp.  Nothing is logged, persisted, or
// sent to any SmartRetailX-owned service.
export function MfaSetupPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const email = (auth.user?.profile.email as string | undefined) ?? "smartretailx-user";

  const [initError, setInitError] = useState<string | null>(null);
  const [setupUri, setSetupUri] = useState<string | null>(null);
  const [sharedSecret, setSharedSecret] = useState<string | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [showManualKey, setShowManualKey] = useState(false);
  const [code, setCode] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const startSetup = useCallback(async () => {
    setInitError(null);
    setSetupUri(null);
    setSharedSecret(null);
    setQrDataUrl(null);
    setCode("");
    setVerifyError(null);
    try {
      const setup = await beginTotpSetup(email);
      setSharedSecret(setup.sharedSecret);
      setSetupUri(setup.setupUri);
      const dataUrl = await QRCode.toDataURL(setup.setupUri, {
        errorCorrectionLevel: "M",
        margin: 1,
        width: 220,
      });
      setQrDataUrl(dataUrl);
    } catch (err) {
      const mapped = friendlyAuthError(err);
      setInitError(mapped.detail ?? mapped.headline);
    }
  }, [email]);

  useEffect(() => {
    void startSetup();
    // Clear the shared secret + URI on unmount as a defensive belt-and-
    // braces to the plain component state.
    return () => {
      setSharedSecret(null);
      setSetupUri(null);
      setQrDataUrl(null);
    };
  }, [startSetup]);

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (verifying || !code || code.length !== 6) return;
    setVerifying(true);
    setVerifyError(null);
    try {
      await verifyAndActivateTotp(code);
      // Success: wipe the transient secret + URI from state immediately;
      // the QR data URL is likewise cleared to prevent screenshots of the
      // success screen from carrying the seed.
      setSharedSecret(null);
      setSetupUri(null);
      setQrDataUrl(null);
      setDone(true);
    } catch (err) {
      const mapped = friendlyAuthError(err, "verify");
      setVerifyError(mapped.detail ?? mapped.headline);
    } finally {
      setVerifying(false);
    }
  }

  if (done) {
    return (
      <section className="security-page">
        <div className="form-card security-card">
          <h1>Multi-factor authentication enabled</h1>
          <p className="security-description">
            Your account is now protected by an authenticator app. From your
            next sign-in you'll be asked for a 6-digit code after your password.
          </p>
          <button
            type="button"
            className="auth-submit-btn"
            onClick={() => navigate("/profile/security", { replace: true })}
          >
            Back to Security
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="security-page">
      <div className="form-card security-card">
        <h1>Set up authenticator</h1>
        <p className="security-description">
          Scan the QR code with any TOTP-compatible authenticator app (for
          example the app you already use for banking or work sign-in), then
          enter the current 6-digit code the app displays.
        </p>

        {initError && (
          <div className="alert-error" role="alert">
            {initError}
            <div style={{ marginTop: "0.5rem" }}>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => void startSetup()}
              >
                Try again
              </button>
            </div>
          </div>
        )}

        {qrDataUrl && (
          <div className="mfa-qr" aria-label="Authenticator app setup QR code">
            <img
              src={qrDataUrl}
              alt="Scan this QR code with your authenticator app"
              width={220}
              height={220}
            />
          </div>
        )}

        {sharedSecret && (
          <div className="mfa-manual">
            <button
              type="button"
              className="linkish"
              onClick={() => setShowManualKey((v) => !v)}
            >
              {showManualKey ? "Hide manual setup key" : "Can't scan the QR code?"}
            </button>
            {showManualKey && (
              <>
                <p className="auth-hint">
                  If your app doesn't scan QR codes, enter this key manually.
                  Do not share this key with anyone.
                </p>
                <code className="mfa-manual-key" aria-label="Manual setup key">
                  {sharedSecret}
                </code>
              </>
            )}
          </div>
        )}

        <form onSubmit={submit} noValidate>
          <label htmlFor="mfa-setup-code">
            6-digit code from your authenticator
          </label>
          <input
            id="mfa-setup-code"
            name="code"
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            pattern="[0-9]{6}"
            value={code}
            onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
            disabled={verifying || !setupUri}
            required
          />

          {verifyError && (
            <div className="alert-error" role="alert">
              {verifyError}
            </div>
          )}

          <button
            type="submit"
            className="auth-submit-btn"
            disabled={verifying || !setupUri || code.length !== 6}
          >
            {verifying ? "Verifying…" : "Verify and enable"}
          </button>
        </form>

        <div className="auth-links">
          <Link to="/profile/security">Cancel setup</Link>
          <button
            type="button"
            className="linkish"
            onClick={() => void startSetup()}
            disabled={verifying}
          >
            Restart setup
          </button>
        </div>
      </div>
    </section>
  );
}
