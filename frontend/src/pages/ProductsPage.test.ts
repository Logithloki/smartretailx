import { describe, expect, it, vi } from "vitest";
import type { Product, ProductListResponse } from "../api/types";
import { fetchAuthoritativeProductUpdates } from "./catalogueRefresh";

const product = (productId: string): Product => ({
  productId,
  productName: `Product ${productId}`,
  price: "12.00",
  category: "General",
  description: null,
  basePrice: "15.00",
  effectivePrice: "12.00",
  promotion: { promotionId: "promo-live" },
  active: true,
});

describe("authoritative catalogue refresh", () => {
  it("refetches affected products and never accepts a WebSocket price", async () => {
    const fetcher = vi.fn(async (_token: string, path: string) => product(path.split("/").at(-1)!));

    const result = await fetchAuthoritativeProductUpdates("token", ["prod-1", "prod-2"], fetcher);

    expect(fetcher.mock.calls.map((call) => call[1])).toEqual([
      "/v1/products/prod-1",
      "/v1/products/prod-2",
    ]);
    expect(result).toEqual([product("prod-1"), product("prod-2")]);
  });

  it("refetches the complete catalogue for a category promotion", async () => {
    const response: ProductListResponse = { products: [product("prod-3")], count: 1 };
    const fetcher = vi.fn(async (token: string, path: string) => {
      expect(token).toBe("token");
      expect(path).toBe("/v1/products");
      return response;
    });

    const result = await fetchAuthoritativeProductUpdates("token", [], fetcher);

    expect(fetcher).toHaveBeenCalledOnce();
    expect(fetcher.mock.calls[0][1]).toBe("/v1/products");
    expect(result).toEqual(response.products);
  });
});
