# SmartRetailX SPA

React and TypeScript single-page application for the mandatory customer and
administrator UI.

## Authentication

The browser uses Cognito Hosted UI (classic) through
`react-oidc-context` and `oidc-client-ts`:

1. the user is redirected to Cognito;
2. Cognito returns an authorization code and state;
3. `oidc-client-ts` validates the callback and completes the PKCE exchange;
4. the access token is attached to `/v1` API requests;
5. API Gateway and the FastAPI service both validate the token;
6. UI roles are read only from the `cognito:groups` claim.

The SPA does not collect passwords or call `USER_PASSWORD_AUTH`. OIDC user and
transaction state use `sessionStorage`, not persistent `localStorage`.

## Runtime configuration

The immutable bundle fetches `/config.json` with `cache: no-store` before React
starts. `src/config/runtime-config.ts` validates every field.

| Field | Meaning |
|---|---|
| `apiBaseUrl` | Empty for same-origin CloudFront `/v1`, or an API origin without a path |
| `websocketUrl` | `wss://` WebSocket stage URL |
| `cognitoAuthority` | Cognito issuer/discovery URL |
| `cognitoDomain` | Cognito Hosted UI domain used for logout |
| `cognitoClientId` | Public SPA client ID; never a client secret |
| `redirectUri` | Allow-listed `/callback` URL |
| `logoutUri` | Allow-listed post-logout URL |
| `environment` | `local`, `sandbox`, `development`, `test`, `staging`, `production`, or `baseline` |
| `releaseId` | Immutable release identifier shown in deployment metadata |

Production and staging config must use HTTPS/WSS and must not use localhost.
The deployment workflow replaces only `config.json`; it does not rebuild the
SPA artifact.

## Local development

```bash
cd frontend
# Edit public/config.json with the public Cognito/API values for your target.
npm ci
npm run dev
```

Open `http://localhost:5173`. The Cognito app client must allow
`http://localhost:5173/callback` and `http://localhost:5173/` only for the
local/development profile.

## Quality commands

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

The production build includes a placeholder `config.json`; deployment creates
the environment-specific file separately as release metadata.
