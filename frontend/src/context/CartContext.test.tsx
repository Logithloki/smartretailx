import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { CartProvider, useCart } from "./CartContext";
import type { Product } from "../api/types";

const productA: Product = {
  productId: "p-a",
  productName: "Widget A",
  price: "10.00",
  category: "Test",
  description: null,
  basePrice: null,
  effectivePrice: null,
  promotion: null,
  active: true,
};
const productB: Product = {
  productId: "p-b",
  productName: "Widget B",
  price: "5.00",
  category: "Test",
  description: null,
  basePrice: null,
  effectivePrice: null,
  promotion: null,
  active: true,
};

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <CartProvider>{children}</CartProvider>
);

describe("CartContext", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => window.localStorage.clear());

  it("exposes an itemCount that sums line quantities", () => {
    const { result } = renderHook(() => useCart(), { wrapper });
    expect(result.current.itemCount).toBe(0);
    act(() => result.current.add(productA));
    act(() => result.current.add(productA));
    act(() => result.current.add(productB));
    expect(result.current.itemCount).toBe(3);
    act(() => result.current.remove(productA.productId));
    expect(result.current.itemCount).toBe(1);
    act(() => result.current.clear());
    expect(result.current.itemCount).toBe(0);
  });

  it("persists cart lines to localStorage across mounts", () => {
    // Mount 1: populate cart.
    const first = renderHook(() => useCart(), { wrapper });
    act(() => first.result.current.add(productA));
    act(() => first.result.current.add(productA));
    first.unmount();

    // Mount 2 (simulates a page reload): should rehydrate from storage.
    const second = renderHook(() => useCart(), { wrapper });
    expect(second.result.current.itemCount).toBe(2);
    expect(second.result.current.lines[0].product.productId).toBe("p-a");
    expect(second.result.current.lines[0].quantity).toBe(2);
  });

  it("silently discards corrupt localStorage payloads", () => {
    window.localStorage.setItem("smartretailx.cart.v1", "not-json{");
    const { result } = renderHook(() => useCart(), { wrapper });
    expect(result.current.itemCount).toBe(0);
    expect(result.current.lines).toEqual([]);
  });

  it("caps a single line at 100 units and rejects <1", () => {
    const { result } = renderHook(() => useCart(), { wrapper });
    act(() => result.current.add(productA));
    act(() => result.current.setQuantity(productA.productId, 5000));
    expect(result.current.lines[0].quantity).toBe(100);
    act(() => result.current.setQuantity(productA.productId, -3));
    expect(result.current.lines[0].quantity).toBe(1);
  });
});
