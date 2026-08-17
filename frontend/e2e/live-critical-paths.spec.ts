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
  await page.goto(baseURL);
  await page.getByRole("button", { name: "Continue to secure sign in" }).click();
  // Cognito Hosted UI renders a hidden username input for federated flows
  // in addition to the visible primary form, so `:visible` disambiguates
  // without depending on DOM ordering.
  await page.locator('input[name="username"]:visible').first().fill(account.username);
  await page.locator('input[name="password"]:visible').first().fill(account.password);
  await page.locator('button[name="signInSubmitButton"]:visible, input[name="signInSubmitButton"]:visible').first().click();
  await expect(page).toHaveURL(/\/products/);
  await expect(page.getByRole("heading", { name: /Product Catalogue/i })).toBeVisible();
}

test.describe("customer critical journey", () => {
  test.skip(!baseURL || !customer.username || !customer.password, "live customer credentials are not configured");

  test("sign in, list products, place order, read history and receive terminal status", async ({ page }) => {
    await hostedUiLogin(page, customer);
    await expect(page.locator(".product-card").first()).toBeVisible();

    await page.getByRole("link", { name: "New Order" }).click();
    await expect(page.getByRole("heading", { name: "New Order Checkout" })).toBeVisible();
    await page.getByRole("button", { name: "Confirm & Place Order" }).click();

    await expect(page).toHaveURL(/\/orders\?highlight=/);
    await expect(page.getByRole("heading", { name: /My Orders/ })).toBeVisible();
    await expect(page.locator("tbody tr.highlight")).toBeVisible();
    await expect(page.locator("tbody tr.highlight .badge")).toHaveText(/CONFIRMED|REJECTED/, { timeout: 45_000 });
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
    await productRow.getByRole("button", { name: /Delete/i }).click();
    await expect(page.getByText(productId, { exact: true })).toHaveCount(0);
  });
});
