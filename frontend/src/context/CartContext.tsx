import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { Product } from "../api/types";

export type CartLine = { product: Product; quantity: number };

type CartApi = {
  lines: CartLine[];
  itemCount: number;
  add: (product: Product) => void;
  setQuantity: (productId: string, quantity: number) => void;
  remove: (productId: string) => void;
  clear: () => void;
};

const CartContext = createContext<CartApi | null>(null);

// Storage key includes the schema version so older cached payloads that no
// longer match `CartLine` are silently discarded on load instead of causing
// runtime errors after a schema change.
const STORAGE_KEY = "smartretailx.cart.v1";

function readStoredLines(): CartLine[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Defensive: only keep entries that structurally look like CartLine.
    return parsed.filter(
      (entry): entry is CartLine =>
        !!entry &&
        typeof entry === "object" &&
        "product" in entry &&
        "quantity" in entry &&
        typeof (entry as CartLine).quantity === "number" &&
        (entry as CartLine).quantity > 0 &&
        !!(entry as CartLine).product?.productId,
    );
  } catch {
    // Quota exceeded, private-browsing lockdowns, corrupt JSON, etc.
    return [];
  }
}

export function CartProvider({ children }: { children: React.ReactNode }) {
  const [lines, setLines] = useState<CartLine[]>(readStoredLines);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(lines));
    } catch {
      // Failing to persist the cart must never break the UI.
    }
  }, [lines]);

  const add = useCallback((product: Product) => {
    setLines((previous) => {
      const line = previous.find((item) => item.product.productId === product.productId);
      return line
        ? previous.map((item) =>
            item.product.productId === product.productId
              ? { ...item, quantity: Math.min(100, item.quantity + 1) }
              : item,
          )
        : [...previous, { product, quantity: 1 }];
    });
  }, []);

  const setQuantity = useCallback((productId: string, quantity: number) => {
    setLines((previous) =>
      previous.map((item) =>
        item.product.productId === productId
          ? { ...item, quantity: Math.max(1, Math.min(100, quantity)) }
          : item,
      ),
    );
  }, []);

  const remove = useCallback((productId: string) => {
    setLines((previous) => previous.filter((item) => item.product.productId !== productId));
  }, []);

  const clear = useCallback(() => setLines([]), []);

  const itemCount = useMemo(
    () => lines.reduce((sum, line) => sum + line.quantity, 0),
    [lines],
  );

  const value = useMemo<CartApi>(
    () => ({ lines, itemCount, add, setQuantity, remove, clear }),
    [lines, itemCount, add, setQuantity, remove, clear],
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useCart(): CartApi {
  const value = useContext(CartContext);
  if (!value) throw new Error("useCart must be used inside CartProvider");
  return value;
}
