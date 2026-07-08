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
