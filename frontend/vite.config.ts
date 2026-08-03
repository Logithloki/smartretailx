import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite substitutes every VITE_* env var into the JS bundle at build
// time (see frontend/README.md and .env.example). That is why the SPA
// cannot pick up new backend URLs "at runtime" from a config file - the
// values are literal strings baked into the bundle by Rollup. The
// deploy pipeline injects VITE_API_BASE_URL, VITE_COGNITO_AUTHORITY,
// VITE_COGNITO_CLIENT_ID, and VITE_COGNITO_REDIRECT_URI as workflow env
// vars before `npm run build`.
export default defineConfig({
  plugins: [react()],
  server: {
    // Cognito's Hosted UI must have this exact origin pre-registered as
    // a callback URL (Terraform seeds it in aws_cognito_user_pool_client).
    port: 5173,
    strictPort: true,
  },
  build: {
    // Fingerprinted asset names + immutable cache header (set by the CI
    // `aws s3 sync` step) give indefinite CDN caching without stale-
    // bundle bugs.
    outDir: "dist",
    sourcemap: false,
  },
});
