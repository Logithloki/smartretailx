import { describe, expect, it } from "vitest";
import type { CartLine } from "../context/CartContext";
import type { Product } from "../api/types";
import { validateAvailability } from "./CartPage";

const product: Product = {
  productId: "p1",
  productName: "Laptop",
  price: "10.00",
  category: "electronics",
  description: null,
  basePrice: "10.00",
  effectivePrice: "10.00",
  promotion: null,
  active: true,
};

const line = (quantity: number): CartLine => ({ product, quantity });

describe("validateAvailability", () => {
  it("rejects an out-of-stock item", () => {
    expect(validateAvailability([line(1)], { p1: 0 })).toMatch(/out of stock/i);
  });

  it("rejects a quantity above the latest known availability", () => {
    expect(validateAvailability([line(3)], { p1: 2 })).toMatch(/only 2/i);
  });

  it("allows a line when the latest known quantity is sufficient", () => {
    expect(validateAvailability([line(2)], { p1: 2 })).toBeNull();
  });
});
