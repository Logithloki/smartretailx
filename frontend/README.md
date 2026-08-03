# SmartRetailX SPA

Vite + React + TypeScript single-page application. Backlog item 27 (mandatory
per lecturer ruling H.2). Week 5 D4 milestone is *auth end-to-end proven* — a
signed-in user can call `GET /v1/products` with the bearer token attached and
render the response. Feature build-out lives in W6 D1–3 (backlog items 28–30).

## Auth stack

- **Cognito Hosted UI** — the same user pool the HTTP API's JWT authoriser
  validates against. There is no separate identity provider.
- **`react-oidc-context`** wraps [`oidc-client-ts`] to give React a
  spec-OpenID-Connect client (~15 KB), rather than the ~200 KB Amplify Auth
  runtime. Swapping Cognito for Auth0 / Okta / Keycloak later would not
  touch a single page component.
- **Authorization Code + PKCE** (RFC 7636). Public SPAs cannot keep a client
  secret, so PKCE replaces the confidential-client assumption: the browser
  generates a random `code_verifier`, sends its SHA-256 hash as
  `code_challenge` on `/authorize`, and presents the raw verifier on `/token`.
  Cognito rejects the exchange if the verifier does not hash to the challenge,
  so an attacker who intercepts the redirect code cannot spend it.

## Environment variables (build-time)

Copy `.env.example` to `.env` and fill in the values.

| Var                          | Where to get it                                                    |
| ---------------------------- | ------------------------------------------------------------------ |
| `VITE_API_BASE_URL`          | `terraform output api_endpoint` for local dev, or `https://<cf>` in prod |
| `VITE_COGNITO_AUTHORITY`     | `https://cognito-idp.<region>.amazonaws.com/<user-pool-id>`         |
| `VITE_COGNITO_CLIENT_ID`     | `terraform output cognito_app_client_id`                            |
| `VITE_COGNITO_REDIRECT_URI`  | `http://localhost:5173/callback` locally; `https://<cf>/callback` in prod |

These are *build-time* only. Vite inlines every `import.meta.env.VITE_*`
reference into the JS bundle during `vite build`; there is no runtime lookup.
The trade-off:

- **Pro** — one HTTP round-trip fewer on first paint (no `/config.json` fetch),
  and a broken config fails fast (`AuthProvider` throws) instead of rendering
  a half-broken UI against the wrong IdP.
- **Con** — new backend URLs require a rebuild + redeploy. Acceptable because
  the URLs move exactly twice in this project's life (dev → prod cutover).

`.env` is git-ignored. In CI (`.github/workflows/deploy.yml`) these are
injected from GitHub repository variables, not secrets: they are all public
(client_id, hosted-UI URL) and end up in a JS bundle anyway.

## Local development

```bash
cd frontend
cp .env.example .env
# edit .env — see the table above
npm install
npm run dev
# open http://localhost:5173
```

Prerequisites on real AWS side:

1. `terraform apply -var="live=true"` so the Cognito user pool, HTTP API,
   and (if you want to test against prod) CloudFront exist.
2. Confirm the Terraform `aws_cognito_user_pool_client.spa` has
   `http://localhost:5173/callback` in `callback_urls`
   (`infra/security.tf` already does — this is a no-op check).
3. Start the four ECS services locally (`docker compose up`) or point
   `VITE_API_BASE_URL` at the deployed API GW URL.

## Deploy

See `.github/workflows/deploy.yml` — the `deploy-spa` job builds this
directory, syncs `dist/` to the SPA S3 bucket, and invalidates
CloudFront `/*`. Immutable cache headers on the fingerprinted assets +
`no-cache` on `index.html` prevent stale-bundle bugs across deploys.

## What is *not* in this scaffold yet

- Full CRUD pages (products admin, place order, my orders with WS live
  status, admin stock). Tracked in backlog 28–30, W6 D1–3.
- Design system pass. Styling here is minimal on purpose.
- Playwright / Vitest tests. Frontend testing goes into W6 testing week.
