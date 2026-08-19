import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/useAuth";
import {
  disableTotp,
  isCiAutomationEmail,
  loadMfaStatus,
} from "../auth/mfa-service";
import { friendlyAuthError } from "../auth/cognito-errors";

// /profile/security — the ONLY profile-area page shipped in PR C.  PR D
// will add the surrounding profile experience (given_name / family_name /
// change password / nav dropdown).  This page reads the authoritative MFA
// status from Cognito and offers Enable / Disable actions on the TOTP
// factor.  Status is never cached in application storage; every render
// reflects a fresh fetchMFAPreference call.
export function SecurityPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const email = (auth.user?.profile.email as string | undefined) ?? null;
  const isCi = isCiAutomationEmail(email);

  const [loading, setLoading] = useState(true);
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [askDisable, setAskDisable] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const status = await loadMfaStatus();
      setEnabled(status.enabled);
      setError(null);
    } catch (err) {
      const mapped = friendlyAuthError(err);
      setError(mapped.detail ?? mapped.headline);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function beginEnable(): Promise<void> {
    if (busy || isCi) return;
    setError(null);
    setFlash(null);
    navigate("/auth/mfa/setup");
  }

  async function confirmDisable(): Promise<void> {
    if (busy) return;
    setBusy(true);
    setError(null);
    setFlash(null);
    try {
      await disableTotp();
      setAskDisable(false);
      await refresh();
      setFlash("Multi-factor authentication is now disabled.");
    } catch (err) {
      const mapped = friendlyAuthError(err);
      setError(mapped.detail ?? mapped.headline);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="security-page">
      <div className="page-header">
        <div className="page-title-group">
          <h1>Security</h1>
          <p>Manage the authentication protections on your SmartRetailX account.</p>
        </div>
      </div>

      {error && (
        <div className="alert-error" role="alert">
          {error}
        </div>
      )}
      {flash && (
        <div className="alert-success" role="status">
          {flash}
        </div>
      )}

      <div className="form-card security-card">
        <h2 className="security-heading">Multi-Factor Authentication</h2>
        <p className="security-description">
          When enabled, sign-in requires the current 6-digit code from an
          authenticator app on your phone in addition to your password.
        </p>

        <div className="security-status" aria-live="polite">
          <span className="security-status-label">Status</span>
          <span className={`role-pill ${enabled ? "admin" : "customer"}`}>
            {loading ? "Loading…" : enabled ? "Enabled" : "Disabled"}
          </span>
        </div>

        {isCi && (
          <div className="alert-info" role="status">
            This looks like a dedicated CI automation account. MFA enrolment is
            managed operationally for those accounts and is disabled from the UI
            to prevent accidental lockout of the runtime-mint scripts. This is a
            usability guard, not a security boundary.
          </div>
        )}

        {!loading && !enabled && !isCi && (
          <button
            type="button"
            className="auth-submit-btn security-cta"
            onClick={() => void beginEnable()}
            disabled={busy}
          >
            Set up authenticator
          </button>
        )}

        {!loading && enabled && (
          <button
            type="button"
            className="btn btn-secondary security-cta"
            onClick={() => setAskDisable(true)}
            disabled={busy}
          >
            Disable MFA
          </button>
        )}

        {askDisable && (
          <div className="security-confirm" role="alertdialog" aria-labelledby="disable-mfa-heading">
            <h3 id="disable-mfa-heading">Disable multi-factor authentication?</h3>
            <p>
              Your account will only require your password to sign in. You can
              re-enable MFA any time from this page.
            </p>
            <div className="security-confirm-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setAskDisable(false)}
                disabled={busy}
              >
                Cancel
              </button>
              <button
                type="button"
                className="auth-submit-btn"
                onClick={() => void confirmDisable()}
                disabled={busy}
              >
                {busy ? "Disabling…" : "Disable MFA"}
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="form-card security-card">
        <h2 className="security-heading">Lost your authenticator?</h2>
        <p className="security-description">
          If you cannot enter a valid TOTP code and cannot access the device
          you enrolled, please contact a SmartRetailX administrator. There is
          no self-service bypass for a lost authenticator — an authorised
          administrator will reset your MFA preference so you can sign in with
          your password and re-enrol a new device.
        </p>
      </div>
    </section>
  );
}
