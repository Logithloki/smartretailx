import { describe, expect, it } from "vitest";
import type { PromotionDraft } from "../api/types";
import { toPromotionWrite } from "./promotionForm";

const draft: PromotionDraft = {
  promotionId: "summer-sale",
  name: "Summer sale",
  discountPercent: "15.00",
  scope: "PRODUCT",
  productIdsText: "prod-1, prod-2, prod-1",
  category: "",
  startsAt: "2026-08-12T08:00",
  endsAt: "2026-08-20T20:00",
  enabled: true,
};

describe("promotion administration payloads", () => {
  it("creates a deduplicated product-scoped write with UTC boundaries", () => {
    const write = toPromotionWrite(draft, true);

    expect(write.promotionId).toBe("summer-sale");
    expect(write.productIds).toEqual(["prod-1", "prod-2"]);
    expect(write.category).toBeUndefined();
    expect(write.startsAt).toMatch(/Z$/);
    expect(write.endsAt).toMatch(/Z$/);
  });

  it("creates a category-scoped write without stale product identifiers", () => {
    const write = toPromotionWrite(
      { ...draft, scope: "CATEGORY", category: "Electronics" },
      false,
    );

    expect(write.promotionId).toBeUndefined();
    expect(write.productIds).toEqual([]);
    expect(write.category).toBe("Electronics");
  });
});
