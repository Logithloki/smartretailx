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

export type OrderStatus = "PENDING" | "CONFIRMED" | "REJECTED" | "CANCEL_PENDING" | "CANCELLED";
export type FulfilmentStatus = "NOT_STARTED" | "PACKING" | "DISPATCHED" | "OUT_FOR_DELIVERY" | "DELIVERED";

export interface OrderItem {
  productId: string;
  productName: string;
  quantity: number;
  baseUnitPrice: string;
  effectiveUnitPrice: string;
  unitDiscount: string;
  lineDiscount: string;
  lineTotal: string;
  promotionId: string | null;
}

export interface Order {
  orderId: string;
  userId: string;
  status: OrderStatus;
  fulfilmentStatus: FulfilmentStatus;
  items: OrderItem[];
  subtotal: string;
  discountTotal: string;
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
  items: Array<Pick<OrderItem, "productId" | "quantity">>;
}

export interface OrderSummaryResponse {
  orderId: string;
  url: string;
}

export interface Product {
  productId: string;
  productName: string;
  price: string;
  category: string;
  description: string | null;
  basePrice: string | null;
  effectivePrice: string | null;
  promotion: { promotionId: string } | null;
  active: boolean;
}

export interface ProductListResponse {
  products: Product[];
  count: number;
}

export interface Availability { productId: string; quantity: number; available: boolean; }
export interface AvailabilityResponse { availability: Availability[]; count: number; }

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

export interface UserProfile {
  userId: string;
  username: string;
  email: string;
  groups: string[];
  userStatus?: string;
  createdAt?: string;
}

export interface UserListResponse {
  users: UserProfile[];
  nextToken?: string | null;
}

export type PromotionScope = "PRODUCT" | "CATEGORY";
export type PromotionLifecycleState = "SCHEDULED" | "ACTIVE" | "EXPIRED" | "DISABLED";

export interface Promotion {
  promotionId: string;
  name: string;
  discountPercent: string;
  scope: PromotionScope;
  productIds: string[];
  category: string | null;
  startsAt: string;
  endsAt: string;
  enabled: boolean;
  lifecycleState: PromotionLifecycleState;
  lifecycleVersion: number;
}

export interface PromotionListResponse {
  promotions: Promotion[];
  count: number;
}

export interface PromotionDraft {
  promotionId: string;
  name: string;
  discountPercent: string;
  scope: PromotionScope;
  productIdsText: string;
  category: string;
  startsAt: string;
  endsAt: string;
  enabled: boolean;
}

export interface PromotionWrite {
  promotionId?: string;
  name: string;
  discountPercent: string;
  scope: PromotionScope;
  productIds: string[];
  category?: string;
  startsAt: string;
  endsAt: string;
  enabled: boolean;
}
