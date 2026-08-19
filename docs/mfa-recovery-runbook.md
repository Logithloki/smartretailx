# SmartRetailX MFA recovery runbook

SmartRetailX supports **optional TOTP MFA** per Cognito user pool. There is
**no self-service bypass** for a lost authenticator — that is a deliberate
design decision. This runbook is the only supported path for helping a locked-
out user regain access.

## What "locked out" means

A user is locked out for MFA reasons when **all** of the following are true:

1. Their account has `SoftwareTokenMfaSettings.Enabled = true`.
2. They cannot enter a valid 6-digit TOTP code (lost or wiped device, phone
   replaced without exporting the authenticator, etc.).
3. They still remember their password. (If they've also lost the password,
   route them through Forgot Password first — that's a separate flow.)

The user's normal flow now stops at the MFA challenge screen after the
password step. They can no longer complete sign-in.

## What is NOT supported

- ❌ No "Skip MFA" button in the SmartRetailX UI.
- ❌ No master recovery code that bypasses TOTP.
- ❌ No hidden API endpoint that clears MFA for the caller.
- ❌ No customer-support-owned admin action outside the documented procedure.

Any request to add one of these should be refused.

## Supported recovery procedure

The user contacts a SmartRetailX administrator (email/ticket). The
administrator confirms the user's identity through the normal SmartRetailX
account-holder verification process (out of scope for this document — treat as
your regular support identity check), then runs **one** of:

### Option 1 — clear the MFA preference only (recommended)

The user still remembers their password. Clear only their MFA setting:

```bash
aws cognito-idp admin-set-user-mfa-preference \
  --region eu-west-1 \
  --user-pool-id <POOL_ID> \
  --username <USER_EMAIL> \
  --software-token-mfa-settings Enabled=false,PreferredMfa=false
```

The user now signs in with their password only. They should immediately go to
**Security → Set up authenticator** and enrol a new device.

### Option 2 — force a password reset (if identity confidence is lower)

Use this if the identity check turned up anything unusual. This invalidates
the current session and forces the user to reset their password before they
can proceed:

```bash
aws cognito-idp admin-reset-user-password \
  --region eu-west-1 \
  --user-pool-id <POOL_ID> \
  --username <USER_EMAIL>

aws cognito-idp admin-set-user-mfa-preference \
  --region eu-west-1 \
  --user-pool-id <POOL_ID> \
  --username <USER_EMAIL> \
  --software-token-mfa-settings Enabled=false,PreferredMfa=false
```

The user receives a Cognito password-reset email, completes the reset in the
SmartRetailX UI, signs in, and re-enrols MFA.

## Which pool for which environment

| Environment | Pool ID |
|---|---|
| Development (baseline) | `eu-west-1_QutfhUEHK` |
| Test | `eu-west-1_L01L7Po79` |
| Staging | `eu-west-1_kYIvUeRUp` |
| Production | not provisioned |

The administrator needs `cognito-idp:AdminSetUserMFAPreference` (and, for
Option 2, `cognito-idp:AdminResetUserPassword`) on the target pool.

## What to log

Only ever log:

- **Who** was recovered (`admin-set-user-mfa-preference` returns no PII beyond
  the username the operator typed).
- **Which pool**.
- **When**.
- **Which administrator ran the command** (from AWS CloudTrail).

**Never log**: the user's password, any previous TOTP secret, or the user's
new TOTP secret. TOTP secrets are only ever exposed to the user's browser
during enrolment and are never stored by SmartRetailX.

## CI accounts

The dedicated CI/E2E identities matching
`^ci-(smoke|customer|admin)-(development|test|staging)@example\.com$` are
**not permitted to enrol MFA** through the SmartRetailX UI. If one of them
somehow does end up MFA-enrolled (e.g. via the AWS console), the recovery
procedure above is the only supported unblock. Long term, prefer never
enrolling them in the first place.
