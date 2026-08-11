import type { PromotionDraft, PromotionWrite } from "../api/types";

export function toPromotionWrite(draft: PromotionDraft, includeId: boolean): PromotionWrite {
  const productIds = draft.scope === "PRODUCT"
    ? [...new Set(draft.productIdsText.split(",").map((value) => value.trim()).filter(Boolean))]
    : [];
  return {
    ...(includeId ? { promotionId: draft.promotionId.trim() } : {}),
    name: draft.name.trim(),
    discountPercent: draft.discountPercent,
    scope: draft.scope,
    productIds,
    ...(draft.scope === "CATEGORY" ? { category: draft.category.trim() } : {}),
    startsAt: new Date(draft.startsAt).toISOString(),
    endsAt: new Date(draft.endsAt).toISOString(),
    enabled: draft.enabled,
  };
}
