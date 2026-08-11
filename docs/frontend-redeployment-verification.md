# SmartRetailX P0 frontend redeployment verification

Date: 11 August 2026  
Environment: `baseline`  
Release: `3c3f37731af8-p0-20260811T052611Z`  
Result: **PASS WITH WARNINGS**

## 1. Original root cause

The live S3 SPA bucket contained only `index.html` and two stale hashed assets. `/config.json` and `/release.json` were absent. CloudFront's SPA custom-error response converted the missing `config.json` request into HTTP 200 containing `index.html`, so `loadRuntimeConfig()` failed when parsing HTML as JSON before React rendered.

Before deployment, the live index referenced:

- `assets/index-DJ5VqSqb.js`;
- `assets/index-BsOVpHfB.css`.

The validated current build generated:

- `assets/index-PdMpsUz6.js`;
- `assets/index-DeQLCTJE.css`.

## 2. Deployment method

The operation followed `.github/workflows/reusable/deploy-frontend.yml` semantics rather than creating a second deployment mechanism:

1. run lint, unit tests, typecheck and production build;
2. materialise the public environment-specific runtime configuration;
3. store the five-file release under `releases/<releaseId>/`;
4. synchronise only the root `assets/` prefix with `--delete`;
5. upload the three no-cache live pointer files;
6. invalidate only the three pointer paths and wait for completion.

No Terraform, ECS, Lambda, Cognito, API Gateway, database, network, GitHub or Terraform-state action was performed.

## 3. Local quality and runtime validation

Fresh results immediately before deployment:

- `npm run lint`: pass;
- `npm test`: 3 files / 8 tests pass;
- `npm run typecheck`: pass;
- `npm run build`: pass, 42 modules transformed.

`dist/` contained `index.html`, `assets/`, `config.json`, and `release.json`. Both JSON files parsed successfully; their release IDs matched. `index.html` referenced both existing current assets. Runtime validation confirmed:

- API origin: `https://dh46kn0l8se6n.cloudfront.net` (callers append canonical `/v1` paths);
- WebSocket: `wss://ik50k8qsle.execute-api.eu-west-1.amazonaws.com/prod`;
- Cognito authority: `https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_QutfhUEHK`;
- Hosted UI: `https://smartretailx-322551984077.auth.eu-west-1.amazoncognito.com`;
- public client: `270ec376iist6pggvkukqdtjsc`;
- callback/logout: CloudFront HTTPS URLs;
- environment: `baseline`.

No localhost value, placeholder, password, JWT, client secret, AWS credential, internal ALB address or private backend endpoint was present.

## 4. Files uploaded and replaced

Versioned release prefix `releases/3c3f37731af8-p0-20260811T052611Z/`:

- `index.html` — 766 bytes;
- `config.json` — 569 bytes;
- `release.json` — 108 bytes;
- `assets/index-PdMpsUz6.js` — 302,162 bytes;
- `assets/index-DeQLCTJE.css` — 15,079 bytes.

Live root:

- replaced `index.html`;
- created `config.json`;
- created `release.json`;
- uploaded the new JS/CSS assets;
- deleted only `assets/index-DJ5VqSqb.js` and `assets/index-BsOVpHfB.css`.

All five live S3 ETags match local MD5 checksums. S3 versioning remains enabled.

## 5. Content metadata and invalidation

| Object class | Content type | Cache control |
|---|---|---|
| `index.html` | `text/html` | `no-cache,no-store,must-revalidate` |
| `config.json`, `release.json` | `application/json` | `no-cache,no-store,must-revalidate` |
| hashed JavaScript | `application/javascript` | `public,max-age=31536000,immutable` |
| hashed CSS | `text/css` | `public,max-age=31536000,immutable` |

CloudFront invalidation `IF1BTAA4JTOZ0ZCJCEBVGZGY0X` completed for:

- `/index.html`;
- `/config.json`;
- `/release.json`.

The distribution remained enabled and `Deployed`.

## 6. External HTTP verification

| Path | Status | Content type | Bytes | Result |
|---|---:|---|---:|---|
| `/` | 200 | `text/html` | 766 | current index |
| `/config.json` | 200 | `application/json` | 569 | valid baseline JSON |
| `/release.json` | 200 | `application/json` | 108 | matching release ID |
| `/assets/index-PdMpsUz6.js` | 200 | `application/javascript` | 302,162 | current JS |
| `/assets/index-DeQLCTJE.css` | 200 | `text/css` | 15,079 | current CSS |

The live index references only the new hashes. The stale root assets are no longer present.

## 7. SPA render and PKCE result

The live page rendered:

- SmartRetailX heading;
- enterprise platform description;
- managed Cognito sign-in explanation;
- usable **Continue to secure sign in** button;
- PKCE security label.

No fatal or error-level browser console entry was present. Clicking the button reached the Cognito `/login` page. Without recording the challenge value, verifier, state, cookies or tokens, the request was verified to contain:

- `response_type=code`;
- a present 43-character `code_challenge`;
- `code_challenge_method=S256`;
- the correct public client ID;
- the correct CloudFront `/callback` URI.

## 8. Post-deployment safety

All four ECS services remained 1 desired / 1 running / 0 pending with completed rollouts. All four application target groups remained healthy. CloudFront remained `Deployed`. Pre-existing dirty Terraform files were untouched; no Terraform command was run. No secret value was exposed.

## 9. Warning and next action

The frontend P0 defect is resolved. The result is **PASS WITH WARNINGS** only because the complete Cognito login/code exchange and authenticated SPA routing are **BLOCKED BY TEST CREDENTIALS**.

Exact next action: in a separately approved task, use legitimate existing customer/admin test credentials to verify the callback and read-only authenticated pages. Do not create users, create orders, run k6, or mutate application data without separate approval.
