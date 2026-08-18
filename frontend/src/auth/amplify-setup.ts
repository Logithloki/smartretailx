// Configure the Amplify Auth singleton against the runtime Cognito settings
// resolved from /config.json.  Amplify v6 requires a one-time Amplify.configure
// call before any auth API is used; keeping it in its own module makes the
// setup explicit and easy to test.
//
// Cognito remains the authority for authentication.  The React application
// only supplies the UI and passes credentials directly to Amplify, which
// itself talks to Cognito (SRP by default in this configuration).  No
// password is sent to any SmartRetailX-owned backend.
import { Amplify } from "aws-amplify";
import type { RuntimeConfig } from "../config/runtime-config";

function extractUserPoolId(authority: string): string {
  let parsed: URL;
  try {
    parsed = new URL(authority);
  } catch {
    throw new Error(
      "runtime config cognitoAuthority must be an absolute URL ending in a Cognito user pool id",
    );
  }
  const pathParts = parsed.pathname.split("/").filter(Boolean);
  const candidate = pathParts[pathParts.length - 1] ?? "";
  if (!/^[a-z]{2}-[a-z]+-\d+_[A-Za-z0-9]+$/.test(candidate)) {
    throw new Error(
      "runtime config cognitoAuthority must end in a Cognito user pool id",
    );
  }
  return candidate;
}

// Amplify supports userPoolClientId without a client secret.  The SPA client
// is `generate_secret = false` in Terraform, so no secret is ever embedded
// into the browser bundle.
export function configureAmplify(config: RuntimeConfig): void {
  const userPoolId = extractUserPoolId(config.cognitoAuthority);
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId,
        userPoolClientId: config.cognitoClientId,
        signUpVerificationMethod: "code",
        loginWith: {
          email: true,
        },
      },
    },
  });
}

// Exported only for the amplify-setup unit test.
export const __testables = { extractUserPoolId };
