import { describe, expect, it } from "vitest";
import type { CartLine } from "../context/CartContext";
import type { Product } from "../api/types";
import {
  validateAvailability,
  stockLevel,
  LOW_STOCK_THRESHOLD,
} from "./CartPage";

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

  it("rejects when availability is unknown", () => {
    expect(validateAvailability([line(1)], {})).toMatch(/could not be confirmed/i);
  });
});

describe("stockLevel", () => {
  it("returns 'unknown' when product has no availability data", () => {
    expect(stockLevel("p1", {})).toBe("unknown");
  });

  it("returns 'out' when quantity is zero", () => {
    expect(stockLevel("p1", { p1: 0 })).toBe("out");
  });

  it("returns 'out' for negative quantity", () => {
    expect(stockLevel("p1", { p1: -1 })).toBe("out");
  });

  it("returns 'low' at the threshold boundary", () => {
    expect(stockLevel("p1", { p1: LOW_STOCK_THRESHOLD })).toBe("low");
  });

  it("returns 'low' for quantity just above zero", () => {
    expect(stockLevel("p1", { p1: 1 })).toBe("low");
  });

  it("returns 'ok' above the threshold", () => {
    expect(stockLevel("p1", { p1: LOW_STOCK_THRESHOLD + 1 })).toBe("ok");
  });

  it("returns 'ok' for high stock", () => {
    expect(stockLevel("p1", { p1: 100 })).toBe("ok");
  });
});

describe("LOW_STOCK_THRESHOLD", () => {
  it("is a positive integer", () => {
    expect(LOW_STOCK_THRESHOLD).toBeGreaterThan(0);
    expect(Number.isInteger(LOW_STOCK_THRESHOLD)).toBe(true);
  });
});
