import { describe, expect, it } from "vitest";
import { parseRealtimeMessage } from "./useOrderStatusStream";

describe("parseRealtimeMessage", () => {
  it("accepts the public catalogue invalidation contract", () => {
    expect(
      parseRealtimeMessage(
        JSON.stringify({
          type: "catalogue.price-refresh",
          productIds: ["prod-1", "prod-2"],
          revision: 7,
        }),
      ),
    ).toEqual({
      type: "catalogue.price-refresh",
      productIds: ["prod-1", "prod-2"],
      revision: 7,
    });
  });

  it("accepts an empty product list as a full-catalogue invalidation", () => {
    expect(
      parseRealtimeMessage(
        JSON.stringify({ type: "catalogue.price-refresh", productIds: [], revision: 1 }),
      ),
    ).toEqual({ type: "catalogue.price-refresh", productIds: [], revision: 1 });
  });

  it.each([
    "not-json",
    JSON.stringify({ type: "catalogue.price-refresh", productIds: ["prod-1"], revision: "7" }),
    JSON.stringify({ type: "catalogue.price-refresh", productIds: ["prod-1", 2], revision: 7 }),
    JSON.stringify({ type: "catalogue.price-refresh", productIds: ["prod-1"], revision: 7, userId: "private" }),
    JSON.stringify({ type: "order.status-changed", orderId: "order-1", status: "UNKNOWN" }),
  ])("rejects malformed or over-shared messages", (raw) => {
    expect(parseRealtimeMessage(raw)).toBeNull();
  });

  it("accepts live cancellation states", () => {
    expect(
      parseRealtimeMessage(
        JSON.stringify({ type: "order.status-changed", orderId: "order-1", status: "CANCELLED" }),
      ),
    ).toEqual({ type: "order.status-changed", orderId: "order-1", status: "CANCELLED" });
  });
});
