import type { components } from "./schema";

// Types are derived from the generated OpenAPI schema (see schema.d.ts,
// produced by `npm run generate:api`) rather than hand-duplicated here, so
// the frontend can't silently drift from the API contract.
export type Variant = components["schemas"]["VariantOut"];
export type Product = components["schemas"]["ProductOut"];
export type ProductPage = components["schemas"]["ProductPage"];
export type CartItem = components["schemas"]["CartItemOut"];
export type Cart = components["schemas"]["CartOut"];
export type User = components["schemas"]["UserOut"];
export type Session = components["schemas"]["SessionOut"];
export type OrderItem = components["schemas"]["OrderItemOut"];
export type Order = components["schemas"]["OrderOut"];
export type AdminOrder = components["schemas"]["AdminOrderOut"];
export type AdminOrderPage = components["schemas"]["AdminOrderPage"];
export type AdminOrderStatusIn = components["schemas"]["AdminOrderStatusIn"];
export type AdminProductIn = components["schemas"]["AdminProductIn"];
export type AdminProductUpdateIn = components["schemas"]["AdminProductUpdateIn"];
export type AdminVariantCreateIn = components["schemas"]["AdminVariantCreateIn"];
export type AdminVariantUpdateIn = components["schemas"]["AdminVariantUpdateIn"];
export type AuditLogEntry = components["schemas"]["AuditLogOut"];
export type AuditLogPage = components["schemas"]["AuditLogPage"];
export type AddressIn = components["schemas"]["AddressIn"];
export type CheckoutIn = components["schemas"]["CheckoutIn"];
export type CheckoutOut = components["schemas"]["CheckoutOut"];
export type PickupDay = components["schemas"]["PickupDayPublicOut"];
export type PickupSlot = components["schemas"]["PickupSlotOut"];
export type AdminPickupDay = components["schemas"]["AdminPickupDayOut"];
export type AdminPickupDayIn = components["schemas"]["AdminPickupDayIn"];
export type AdminPickupDayUpdateIn = components["schemas"]["AdminPickupDayUpdateIn"];

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  // Spread options first: spreading it last would let a caller's `headers`
  // replace this object wholesale and silently drop the Content-Type.
  const response = await fetch(`/api/v1${path}`, {
    credentials: "include",
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Request failed" }));
    const detail = body.detail ?? "Request failed";
    throw new ApiError(response.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const money = (cents: number) =>
  new Intl.NumberFormat("sv-SE", { style: "currency", currency: "SEK" }).format(cents / 100);

// Pickup happens at a physical location, so pickup times are always shown in the
// café's timezone (Umeå), never the viewer's: a slot stored as 14:00Z must render
// as 16:15-style café wall-clock time for every visitor.
export const CAFE_TIMEZONE = "Europe/Stockholm";

// Compact pickup-time label used on order cards and admin tables, e.g. "9/7, 16:15".
export const formatPickup = (iso: string) => {
  const date = new Date(iso);
  const part = (options: Intl.DateTimeFormatOptions) =>
    new Intl.DateTimeFormat("en-GB", { timeZone: CAFE_TIMEZONE, ...options }).format(date);
  const time = part({ hour: "2-digit", minute: "2-digit", hour12: false });
  return `${part({ day: "numeric" })}/${part({ month: "numeric" })}, ${time}`;
};
