import { expect, Page, test } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL;
const customer = {
  username: process.env.E2E_CUSTOMER_USERNAME,
  password: process.env.E2E_CUSTOMER_PASSWORD,
};
const admin = {
  username: process.env.E2E_ADMIN_USERNAME,
  password: process.env.E2E_ADMIN_PASSWORD,
};

async function hostedUiLogin(page: Page, account: typeof customer): Promise<void> {
  if (!baseURL || !account.username || !account.password) {
    throw new Error("E2E_BASE_URL and the selected E2E account credentials are required");
  }
  // PR A migrated the sign-in flow off Cognito Hosted UI onto a
  // first-party SmartRetailX React form.  Credentials go straight to
  // Amplify Auth (SRP); no more redirect through the Cognito domain.
  await page.goto(baseURL);
  // Wait for the React SPA to hydrate + Amplify to configure before any
  // interaction; without this, locator.fill can race the initial render on
  // slow CI runners.
  await expect(page.getByRole("heading", { name: /^SmartRetailX$/ })).toBeVisible();
  // Target the input controls by role rather than by label — the
  // <label>Email <input/></label> pattern makes getByLabel ambiguous
  // between the label element and the textbox, causing intermittent
  // 60s timeouts on Playwright's locator.fill.
  await page.getByRole("textbox", { name: /email/i }).fill(account.username);
  // Passwords are not textboxes (Playwright reserves that role for
  // type="text"/type="email"), so target them via the label-for id.
  await page.locator("#signin-password").fill(account.password);
  await page.getByRole("button", { name: /^sign in$/i }).click();
  await expect(page).toHaveURL(/\/products/, { timeout: 30_000 });
  await expect(page.getByRole("heading", { name: /Product Catalogue/i })).toBeVisible();
}

test.describe("customer critical journey", () => {
  test.skip(!baseURL || !customer.username || !customer.password, "live customer credentials are not configured");

  test("sign in, list products, place order, read history and receive terminal status", async ({ page }) => {
    await hostedUiLogin(page, customer);
    await expect(page.locator(".product-card").first()).toBeVisible();

    // The catalogue flow is: Add to cart -> /cart -> Confirm order ->
    // in-page "Order confirmed" state -> Track delivery link to /orders.
    // The cart page does not navigate on its own; it renders a "Track
    // delivery" button after the Order Service returns.
    await page.getByRole("button", { name: "Add to cart" }).first().click();
    // The cart nav link should reflect the item count immediately so the
    // shopper knows the button worked without waiting for the cart page.
    await expect(page.getByRole("link", { name: /Cart \(1 item\)/i })).toBeVisible();
    await page.getByRole("link", { name: /Cart/i }).click();
    await expect(page.getByRole("heading", { name: /Cart & checkout/i })).toBeVisible();
    await page.getByRole("button", { name: "Confirm order" }).click();

    await expect(page.getByRole("heading", { name: /Order confirmed/i })).toBeVisible({
      timeout: 30_000,
    });
    await page.getByRole("link", { name: /Track delivery/i }).click();
    await expect(page).toHaveURL(/\/orders(\?|$)/);
    await expect(page.getByRole("heading", { name: /My Orders/ })).toBeVisible();
    await expect(page.locator("tbody tr").first()).toBeVisible();
    // Terminal status may be CONFIRMED (stock available) or REJECTED
    // (insufficient stock).  The Saga's asynchronous transition takes
    // a few seconds after the order is submitted.  Each order row
    // renders two badges (order status + fulfilment status), so the
    // locator has to select the first one specifically instead of
    // relying on strict single-match.
    await expect(page.locator("tbody tr").first().locator(".badge").first()).toHaveText(
      /CONFIRMED|REJECTED/,
      { timeout: 45_000 },
    );
  });

  test("customer is blocked from admin UI and admin API", async ({ page }) => {
    await hostedUiLogin(page, customer);
    await page.goto(`${baseURL}/admin/products`);
    await expect(page.getByText(/Access Restricted/)).toBeVisible();
    const status = await page.evaluate(async () => {
      const key = Object.keys(sessionStorage).find((item) => item.startsWith("oidc.user:"));
      const token = key ? JSON.parse(sessionStorage.getItem(key) ?? "{}").access_token : "";
      return fetch("/v1/products/e2e-forbidden", {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      }).then((response) => response.status);
    });
    expect(status).toBe(403);
  });
});

test.describe("administrator critical journey", () => {
  test.skip(!baseURL || !admin.username || !admin.password, "live admin credentials are not configured");

  test("admin creates and deletes a product, then adjusts inventory", async ({ page }) => {
    await hostedUiLogin(page, admin);
    const productId = `e2e-${Date.now()}`;

    await page.getByRole("link", { name: "Admin: Products" }).click();
    await page.getByPlaceholder("e.g. macbook-pro-16").fill(productId);
    await page.getByPlaceholder("e.g. Smart Retail Laptop X1").fill("E2E Product");
    await page.getByPlaceholder("29.99").fill("1.00");
    await page.getByPlaceholder("e.g. Electronics").fill("Testing");
    await page.getByRole("button", { name: "Create Product" }).click();
    await expect(page.getByText(productId, { exact: true })).toBeVisible();

    await page.getByRole("link", { name: "Admin: Stock" }).click();
    await page.getByPlaceholder(/Search stock table/).fill(productId);
    const row = page.locator("tbody tr").filter({ hasText: productId });
    await row.locator('input[type="number"]').fill("25");
    await row.getByRole("button", { name: "Save Level" }).click();
    await expect(row).toContainText("25 units");

    await page.getByRole("link", { name: "Admin: Products" }).click();
    const productRow = page.locator("tbody tr").filter({ hasText: productId });
    // The admin UI guards Delete with window.confirm.  Playwright
    // auto-dismisses (== cancel) native dialogs unless a handler is
    // registered before the interaction that triggers them.
    page.once("dialog", (dialog) => dialog.accept());
    await productRow.getByRole("button", { name: /Delete/i }).click();
    await expect(page.getByText(productId, { exact: true })).toHaveCount(0);
  });
});
