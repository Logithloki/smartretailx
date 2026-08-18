import { describe, expect, it } from "vitest";
import { formatCurrency, pricesAreEqual } from "./format";

describe("formatCurrency", () => {
  it("formats decimal-string prices with two fraction digits", () => {
    expect(formatCurrency("1299.99")).toBe("£1,299.99");
    expect(formatCurrency("79.9")).toBe("£79.90");
    expect(formatCurrency("1299")).toBe("£1,299.00");
    expect(formatCurrency(0)).toBe("£0.00");
  });

  it("uses thousands separators", () => {
    expect(formatCurrency("1234567.5")).toBe("£1,234,567.50");
  });

  it("returns em-dash for missing or non-numeric input", () => {
    expect(formatCurrency(null)).toBe("—");
    expect(formatCurrency(undefined)).toBe("—");
    expect(formatCurrency("")).toBe("—");
    expect(formatCurrency("not-a-number")).toBe("—");
    expect(formatCurrency(Number.NaN)).toBe("—");
  });
});

describe("pricesAreEqual", () => {
  it("compares numerically regardless of trailing-zero string representation", () => {
    expect(pricesAreEqual("1299.99", "1299.99")).toBe(true);
    expect(pricesAreEqual("1299.9", "1299.90")).toBe(true);
    expect(pricesAreEqual("1299", "1299.00")).toBe(true);
    expect(pricesAreEqual(79.99, "79.99")).toBe(true);
  });

  it("returns false for genuinely different prices", () => {
    expect(pricesAreEqual("1299.99", "999.99")).toBe(false);
    expect(pricesAreEqual("100.00", "100.01")).toBe(false);
  });

  it("returns false when either input is missing or non-numeric", () => {
    expect(pricesAreEqual(null, "1")).toBe(false);
    expect(pricesAreEqual("1", undefined)).toBe(false);
    expect(pricesAreEqual("nope", "1")).toBe(false);
  });
});
