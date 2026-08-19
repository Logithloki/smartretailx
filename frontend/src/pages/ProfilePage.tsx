import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/useAuth";
import {
  disableTotp,
  isCiAutomationEmail,
  loadMfaStatus,
} from "../auth/mfa-service";
import { friendlyAuthError } from "../auth/cognito-errors";
import {
  loadProfileAttributes,
  saveProfileAttributes,
  verifyEmailAttribute,
} from "../auth/profile-service";
import { changePassword } from "../auth/password-service";

export function ProfilePage() {
  const auth = useAuth();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  
  // Profile State
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);
  const [emailVerificationPending, setEmailVerificationPending] = useState(false);
  const [emailVerificationCode, setEmailVerificationCode] = useState("");
  
  // Security/MFA State
  const [mfaEnabled, setMfaEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [askDisable, setAskDisable] = useState(false);
  const isCi = isCiAutomationEmail(email);
  
  // Password State
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [changingPassword, setChangingPassword] = useState(false);

  // Read-only role from claims
  const roleGroups = (auth.user?.profile["cognito:groups"] as string[]) || [];
  const isAdmin = roleGroups.includes("admin");

  const refresh = useCallback(async () => {
    try {
      const [mfaStatus, profile] = await Promise.all([
        loadMfaStatus(),
        loadProfileAttributes(),
      ]);
      setMfaEnabled(mfaStatus.enabled);
      setFirstName(profile.given_name);
      setLastName(profile.family_name);
      setEmail(profile.email);
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

  async function handleProfileSave(e: React.FormEvent) {
    e.preventDefault();
    if (savingProfile) return;
    setSavingProfile(true);
    setError(null);
    setFlash(null);
    
    try {
      const result = await saveProfileAttributes({
        email,
        given_name: firstName,
        family_name: lastName,
      });

      if (result.nextStep?.updateAttributeStep === "CONFIRM_ATTRIBUTE_WITH_CODE") {
        setEmailVerificationPending(true);
        setFlash("A verification code has been sent to your new email address.");
      } else {
        setFlash("Profile updated successfully.");
        await refresh();
      }
    } catch (err) {
      const mapped = friendlyAuthError(err);
      setError(mapped.detail ?? mapped.headline);
    } finally {
      setSavingProfile(false);
    }
  }

  async function handleEmailVerification(e: React.FormEvent) {
    e.preventDefault();
    if (savingProfile) return;
    setSavingProfile(true);
    setError(null);
    setFlash(null);

    try {
      await verifyEmailAttribute(emailVerificationCode);
      setEmailVerificationPending(false);
      setEmailVerificationCode("");
      setFlash("Email verified and profile updated successfully.");
      await refresh();
    } catch (err) {
      const mapped = friendlyAuthError(err);
      setError(mapped.detail ?? mapped.headline);
    } finally {
      setSavingProfile(false);
    }
  }

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    if (changingPassword) return;
    
    if (newPassword !== confirmPassword) {
      setError("New password and confirm password do not match.");
      return;
    }
    
    setChangingPassword(true);
    setError(null);
    setFlash(null);
    
    try {
      await changePassword(currentPassword, newPassword);
      setFlash("Password changed successfully.");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      const mapped = friendlyAuthError(err);
      setError(mapped.detail ?? mapped.headline);
    } finally {
      setChangingPassword(false);
    }
  }

  async function beginEnableMfa(): Promise<void> {
    if (busy || isCi) return;
    setError(null);
    setFlash(null);
    navigate("/auth/mfa/setup");
  }

  async function confirmDisableMfa(): Promise<void> {
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

  if (loading) {
    return <section className="security-page"><p>Loading profile...</p></section>;
  }

  return (
    <section className="security-page">
      <div className="page-header">
        <div className="page-title-group">
          <h1>My Profile</h1>
          <p>Manage your account settings and security preferences.</p>
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

      {/* Profile Section */}
      <div className="form-card security-card">
        <h2 className="security-heading">Profile Details</h2>
        
        {emailVerificationPending ? (
          <form onSubmit={(e) => void handleEmailVerification(e)} className="auth-form" style={{ marginTop: '1rem' }}>
            <p className="security-description">
              Please check your new email inbox for a verification code.
            </p>
            <div className="form-group">
              <label htmlFor="verifyCode">Verification Code</label>
              <input
                id="verifyCode"
                type="text"
                required
                value={emailVerificationCode}
                onChange={(e) => setEmailVerificationCode(e.target.value)}
                autoComplete="one-time-code"
                placeholder="123456"
              />
            </div>
            <button
              type="submit"
              className="auth-submit-btn"
              disabled={savingProfile}
            >
              {savingProfile ? "Verifying…" : "Verify Email"}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              style={{ width: "100%", marginTop: "0.5rem" }}
              onClick={() => setEmailVerificationPending(false)}
              disabled={savingProfile}
            >
              Cancel
            </button>
          </form>
        ) : (
          <form onSubmit={(e) => void handleProfileSave(e)} className="auth-form" style={{ marginTop: '1rem' }}>
            <div className="form-group">
              <label htmlFor="firstName">First name</label>
              <input
                id="firstName"
                type="text"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                autoComplete="given-name"
              />
            </div>
            <div className="form-group">
              <label htmlFor="lastName">Last name</label>
              <input
                id="lastName"
                type="text"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                autoComplete="family-name"
              />
            </div>
            <div className="form-group">
              <label htmlFor="email">Email address</label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
              />
            </div>
            
            <div className="form-group">
              <label>Role</label>
              <div>
                <span className={`role-pill ${isAdmin ? "admin" : "customer"}`}>
                  {isAdmin ? "Admin" : "Customer"}
                </span>
                <span className="security-description" style={{ marginLeft: "1rem", fontSize: "0.8rem" }}>
                  (Read-only)
                </span>
              </div>
            </div>

            <button
              type="submit"
              className="auth-submit-btn security-cta"
              disabled={savingProfile}
              style={{ marginTop: '0.5rem' }}
            >
              {savingProfile ? "Saving…" : "Save Changes"}
            </button>
          </form>
        )}
      </div>

      {/* Change Password Section */}
      <div className="form-card security-card">
        <h2 className="security-heading">Change Password</h2>
        <form onSubmit={(e) => void handleChangePassword(e)} className="auth-form" style={{ marginTop: '1rem' }}>
          <div className="form-group">
            <label htmlFor="currentPassword">Current password</label>
            <input
              id="currentPassword"
              type="password"
              required
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          <div className="form-group">
            <label htmlFor="newPassword">New password</label>
            <input
              id="newPassword"
              type="password"
              required
              minLength={12}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoComplete="new-password"
              aria-describedby="newPassword-hint"
            />
            <span id="newPassword-hint" className="security-description" style={{ fontSize: "0.75rem", display: "block", marginTop: "0.25rem" }}>
              Must be at least 12 characters, including uppercase, lowercase, numbers, and symbols.
            </span>
          </div>
          <div className="form-group">
            <label htmlFor="confirmPassword">Confirm new password</label>
            <input
              id="confirmPassword"
              type="password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
            />
          </div>
          <button
            type="submit"
            className="auth-submit-btn security-cta"
            disabled={changingPassword}
            style={{ marginTop: '0.5rem' }}
          >
            {changingPassword ? "Updating…" : "Update Password"}
          </button>
        </form>
      </div>

      {/* Multi-Factor Authentication Section */}
      <div className="form-card security-card">
        <h2 className="security-heading">Multi-Factor Authentication</h2>
        <p className="security-description">
          When enabled, sign-in requires the current 6-digit code from an
          authenticator app on your phone in addition to your password.
        </p>

        <div className="security-status" aria-live="polite">
          <span className="security-status-label">Status</span>
          <span className={`role-pill ${mfaEnabled ? "admin" : "customer"}`}>
            {mfaEnabled ? "Enabled" : "Disabled"}
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

        {!mfaEnabled && !isCi && (
          <button
            type="button"
            className="auth-submit-btn security-cta"
            onClick={() => void beginEnableMfa()}
            disabled={busy}
          >
            Set up authenticator
          </button>
        )}

        {mfaEnabled && (
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
                onClick={() => void confirmDisableMfa()}
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
