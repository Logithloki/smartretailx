import { apiFetch } from "../api/client";
import type { Product, ProductListResponse } from "../api/types";

type CatalogueFetcher = (token: string, path: string) => Promise<unknown>;

export async function fetchAuthoritativeProductUpdates(
  token: string,
  productIds: string[],
  fetcher: CatalogueFetcher = (accessToken, path) => apiFetch(accessToken, path),
): Promise<Product[]> {
  if (productIds.length === 0) {
    const catalogue = (await fetcher(token, "/v1/products")) as ProductListResponse;
    return catalogue.products;
  }
  return Promise.all(
    productIds.map(
      async (productId) =>
        (await fetcher(token, `/v1/products/${encodeURIComponent(productId)}`)) as Product,
    ),
  );
}
