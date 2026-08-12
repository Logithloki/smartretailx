import { createContext, useContext, useMemo, useState } from "react";
import type { Product } from "../api/types";

export type CartLine = { product: Product; quantity: number };

type CartApi = {
  lines: CartLine[];
  add: (product: Product) => void;
  setQuantity: (productId: string, quantity: number) => void;
  remove: (productId: string) => void;
  clear: () => void;
};

const CartContext = createContext<CartApi | null>(null);

export function CartProvider({ children }: { children: React.ReactNode }) {
  const [lines, setLines] = useState<CartLine[]>([]);
  const value = useMemo<CartApi>(() => ({
    lines,
    add(product) {
      setLines((previous) => {
        const line = previous.find((item) => item.product.productId === product.productId);
        return line
          ? previous.map((item) => item.product.productId === product.productId ? { ...item, quantity: Math.min(100, item.quantity + 1) } : item)
          : [...previous, { product, quantity: 1 }];
      });
    },
    setQuantity(productId, quantity) {
      setLines((previous) => previous.map((item) => item.product.productId === productId ? { ...item, quantity: Math.max(1, Math.min(100, quantity)) } : item));
    },
    remove(productId) { setLines((previous) => previous.filter((item) => item.product.productId !== productId)); },
    clear() { setLines([]); },
  }), [lines]);
  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useCart(): CartApi {
  const value = useContext(CartContext);
  if (!value) throw new Error("useCart must be used inside CartProvider");
  return value;
}
