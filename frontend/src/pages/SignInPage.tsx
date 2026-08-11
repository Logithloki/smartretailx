import { useAuth } from "../context/useAuth";

export function SignInPage() {
  const auth = useAuth();

  return (
    <div className="auth-page-container">
      <div className="auth-card">
        <div className="auth-card-header">
          <h1>SmartRetailX</h1>
          <p>Enterprise AWS Cloud-Native Retail Platform</p>
        </div>

        {auth.error && (
          <div className="alert-error" role="alert">
            Sign-in failed: {auth.error.message}
          </div>
        )}

        <p>
          Sign in through the managed Cognito login page. Passwords and OAuth
          verification data are never handled by this application.
        </p>

        <button
          type="button"
          className="auth-submit-btn"
          disabled={auth.isLoading || auth.activeNavigator === "signinRedirect"}
          onClick={() => void auth.signinRedirect()}
        >
          Continue to secure sign in
        </button>

        <div className="auth-footer-note">
          OAuth 2.0 Authorization Code with PKCE · Secured by AWS Cognito
        </div>
      </div>
    </div>
  );
}
