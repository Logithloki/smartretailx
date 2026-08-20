# Client and authorization acceptance matrix

Date: 20 August 2026
Live environment: Test
Promotion run: `32357279246`
Automated layers: Newman API contracts, Playwright critical journeys and service authorization tests

| Persona | Capability | Expected | Result | Evidence layer |
|---|---|---:|---|---|
| Unauthenticated | Public storefront `/` | 200 | PASS | Playwright storefront journey |
| Unauthenticated | Product API | 401 | PASS | Direct Test probe and Newman JWT-required contract |
| Customer A | Own profile | 200 | PASS | Newman profile contract |
| Customer A | Own order list/detail | 200 | PASS | Newman and Order Service tests |
| Customer A | Customer B order | 404 | PASS | `test_another_users_order_is_404_not_403` |
| Customer A | Own order summary | 200 | PASS | Newman summary contract |
| Customer A | Customer B order summary | 404 | PASS | `test_non_owner_gets_404` |
| Customer A | Admin product mutation | 403 | PASS | Newman and Playwright RBAC checks |
| Customer A | Admin inventory | 403 | PASS | Newman inventory RBAC contract |
| Customer A | Admin fulfilment list/mutation | 403 | PASS | Newman and Playwright RBAC checks |
| Admin | User directory and inventory | 200 | PASS | Newman admin contracts |
| Admin | Fulfilment list and valid transition | 200 | PASS | Newman and Playwright admin journey |
| Admin | Any order summary according to current policy | 200 | PASS | Newman admin summary contract |
| Any authenticated user | Unknown order/summary | 404 | PASS | Newman and service tests |

The matrix preserves intentional 404 responses for cross-customer order resources to avoid confirming that another customer's identifier exists. Frontend route guards are supplementary; the 403/404 results above come from backend authorization tests and live API contracts.
