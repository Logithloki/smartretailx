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

const responsiveViewports = [
  { width: 1440, height: 900 },
  { width: 1366, height: 768 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
] as const;

async function expectNoHorizontalPageOverflow(page: Page): Promise<void> {
  const hasOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(hasOverflow).toBe(false);
}

test.describe("public storefront", () => {
  test.skip(!baseURL, "E2E_BASE_URL is required");

  test("guest storefront renders with working navigation and no horizontal overflow", async ({ page }) => {
    for (const viewport of responsiveViewports) {
      await page.setViewportSize(viewport);
      await page.goto(`${baseURL!.replace(/\/$/, "")}/`);
      await expect(
        page.getByRole("heading", { name: /everything you need/i, level: 1 }),
      ).toBeVisible();
      await expect(
        page.getByRole("img", { name: /shopping cart with everyday groceries/i }),
      ).toBeVisible();
      await expectNoHorizontalPageOverflow(page);

      if (viewport.width >= 1024) {
        await expect(
          page.getByLabel("Primary navigation").getByRole("link", { name: /^sign in$/i }),
        ).toBeVisible();
        await expect(
          page.getByLabel("Primary navigation").getByRole("link", { name: /create account/i }),
        ).toBeVisible();
      } else {
        const menuButton = page.getByRole("button", { name: /open navigation/i });
        await expect(menuButton).toBeVisible();
        await menuButton.click();
        await expect(page.getByRole("button", { name: /close navigation/i })).toHaveAttribute(
          "aria-expanded",
          "true",
        );
        await expect(page.getByRole("link", { name: /^cart \(empty\)$/i })).toBeVisible();
        await expectNoHorizontalPageOverflow(page);
      }
    }

    await expect(page.getByRole("heading", { name: /a thoughtful place to start/i })).toBeVisible();
  });
});

async function hostedUiLogin(page: Page, account: typeof customer): Promise<void> {
  if (!baseURL || !account.username || !account.password) {
    throw new Error("E2E_BASE_URL and the selected E2E account credentials are required");
  }
  // PR A migrated the sign-in flow off Cognito Hosted UI onto a
  // first-party SmartRetailX React form.  Credentials go straight to
  // Amplify Auth (SRP); no more redirect through the Cognito domain.
  //
  // Since the storefront-landing PR, "/" renders the public marketing
  // landing (which also contains an <h1>SmartRetailX</h1>) rather than
  // the sign-in form. Navigate straight to the sign-in route.
  await page.goto(`${baseURL.replace(/\/$/, "")}/login`);
  // Wait for the sign-in form's email input to be attached + hydrated
  // before typing into it (Amplify configuration is async).
  await expect(page.getByRole("textbox", { name: /email/i })).toBeVisible({
    timeout: 30_000,
  });
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

  test("customer can download order summary from order detail", async ({ page }) => {
    await hostedUiLogin(page, customer);

    await page.getByRole("link", { name: /Orders/i }).click();
    await expect(page.getByRole("heading", { name: /My Orders/ })).toBeVisible();

    const firstRow = page.locator("tbody tr").first();
    const hasOrders = await firstRow.isVisible().catch(() => false);
    if (!hasOrders) {
      test.skip();
      return;
    }

    await firstRow.locator("a").first().click();
    await expect(page.getByRole("heading", { name: /Order/ })).toBeVisible();

    const downloadBtn = page.getByRole("button", { name: /Download Order Summary/i });
    await expect(downloadBtn).toBeVisible();

    const popupPromise = page.waitForEvent("popup", { timeout: 15_000 }).catch(() => null);
    const responsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        /\/v1\/orders\/[^/]+\/summary(?:\?|$)/.test(response.url()),
      { timeout: 15_000 },
    );

    await downloadBtn.click();
    const response = await responsePromise;
    expect(response.ok()).toBe(true);
    const payload = (await response.json()) as { downloadUrl?: string };
    expect(payload.downloadUrl).toContain("X-Amz-Signature");

    const popup = await popupPromise;
    await popup?.close();
  });

  test("customer is blocked from admin UI and admin API", async ({ page }) => {
    await hostedUiLogin(page, customer);
    await page.goto(`${baseURL}/admin/products`);
    await expect(page.getByText(/Access Restricted/)).toBeVisible();
    const status = await page.evaluate(async () => {
      // PR A migrated auth to Amplify v6, which stores tokens in
      // localStorage under keys of the form
      //   CognitoIdentityServiceProvider.<clientId>.<userSub>.accessToken
      // Reading it directly here is the least-invasive way to prove that
      // a real customer JWT gets a 403 (not 401) from the admin API.
      const keys = Object.keys(localStorage);
      const accessKey = keys.find(
        (k) => k.startsWith("CognitoIdentityServiceProvider.") && k.endsWith(".accessToken"),
      );
      const token = accessKey ? localStorage.getItem(accessKey) ?? "" : "";
      return fetch("/v1/products/e2e-forbidden", {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      }).then((response) => response.status);
    });
    // 403 = the JWT authoriser accepted the token and the FastAPI RBAC
    // middleware then denied it (correct customer-blocked-from-admin
    // outcome).  401 would mean the token was not sent or was invalid,
    // which would incorrectly pass this assertion for the wrong reason.
    expect(status).toBe(403);
  });

  test("customer commerce pages remain responsive without whole-page overflow", async ({ page }) => {
    await hostedUiLogin(page, customer);
    const routes = [
      { path: "/products", heading: /Product Catalogue/i },
      { path: "/cart", heading: /Cart & checkout/i },
      { path: "/orders", heading: /My Orders/i },
    ];

    for (const viewport of responsiveViewports) {
      await page.setViewportSize(viewport);
      for (const route of routes) {
        await page.goto(`${baseURL}${route.path}`);
        if (route.path === "/cart") {
          await expect(
            page.getByRole("heading", { name: /Cart & checkout|Your cart is empty/i }),
          ).toBeVisible();
        } else {
          await expect(page.getByRole("heading", { name: route.heading })).toBeVisible();
        }
        await expectNoHorizontalPageOverflow(page);
      }
    }
  });
});

test.describe("administrator critical journey", () => {
  test.skip(!baseURL || !admin.username || !admin.password, "live admin credentials are not configured");

  test("admin views fulfilment queue and progresses an order", async ({ page }) => {
    await hostedUiLogin(page, admin);
    await page.getByRole("link", { name: /Admin: Fulfilment/i }).click();
    await expect(page.getByRole("heading", { name: /Admin: Fulfilment/ })).toBeVisible();

    const statsCards = page.locator('[role="status"]');
    await expect(statsCards.first()).toBeVisible();

    const actionableRow = page.locator("tbody tr").filter({
      has: page.getByRole("button", { name: /Start packing/i }),
    });
    const hasActionable = await actionableRow.count();
    if (hasActionable > 0) {
      const orderId = await actionableRow.first().locator("code").textContent();
      await actionableRow.first().getByRole("button", { name: /Start packing/i }).click();

      const updatedRow = page.locator("tbody tr").filter({ hasText: orderId! });
      await expect(
        updatedRow.locator(".badge").filter({ hasText: /PACKING/ }),
      ).toBeVisible({ timeout: 15_000 });

      await updatedRow.click();
      const drawer = page.getByRole("dialog");
      await expect(drawer).toBeVisible();
      await expect(drawer.getByText(orderId!)).toBeVisible();
      await expect(drawer.getByRole("progressbar")).toBeVisible();
    }
  });

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

  test("fulfilment dashboard remains responsive without whole-page overflow", async ({ page }) => {
    await hostedUiLogin(page, admin);
    for (const viewport of responsiveViewports) {
      await page.setViewportSize(viewport);
      await page.goto(`${baseURL}/admin/fulfilment`);
      await expect(page.getByRole("heading", { name: /Admin: Fulfilment/i })).toBeVisible();
      await expectNoHorizontalPageOverflow(page);
    }
  });
});
