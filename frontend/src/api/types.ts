/*
 * TypeScript mirrors of the backend Pydantic models.
 *
 * Kept hand-written rather than generated from an OpenAPI schema at this
 * stage: the backend surface is small (four services, ~15 endpoints) and
 * a generator would add build-time coupling for questionable gain. If
 * the API surface grows past ~40 endpoints, revisit openapi-typescript.
 *
 * Money is `string` on the wire, not `number` - the Python side uses
 * Decimal so no float ever appears (Order.py, Product.py). Every render
 * of a price MUST format the string (never Number() it) or you re-
 * introduce the float-precision bug this design was set up to avoid.
 */

export type OrderStatus = "PENDING" | "CONFIRMED" | "REJECTED";

export interface OrderItem {
  productId: string;
  quantity: number;
  unitPrice: string;
}

export interface Order {
  orderId: string;
  userId: string;
  status: OrderStatus;
  items: OrderItem[];
  totalAmount: string;
  createdAt: string;
  updatedAt: string;
  statusReason: string | null;
}

export interface OrderListResponse {
  orders: Order[];
  count: number;
}

export interface CreateOrderRequest {
  items: OrderItem[];
}

export interface Product {
  productId: string;
  productName: string;
  price: string;
  category: string;
  description: string | null;
}

export interface ProductListResponse {
  products: Product[];
  count: number;
}

export interface ProductCreate {
  productId: string;
  productName: string;
  price: string;
  category: string;
  description?: string | null;
}

export interface ProductUpdate {
  productName?: string;
  price?: string;
  category?: string;
  description?: string | null;
}

export interface StockLevel {
  productId: string;
  quantity: number;
  updatedAt: string | null;
}

export interface StockListResponse {
  stock: StockLevel[];
  count: number;
}

export interface StockAdjustment {
  quantity: number;
}
