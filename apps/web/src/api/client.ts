import type { components } from "./schema";

// Types are derived from the generated OpenAPI schema (see schema.d.ts,
// produced by `npm run generate:api`) rather than hand-duplicated here, so
// the frontend can't silently drift from the API contract.
export type Variant = components["schemas"]["VariantOut"];
export type Product = components["schemas"]["ProductOut"];
export type ProductImage = components["schemas"]["ImageOut"];
export type ProductPage = components["schemas"]["ProductPage"];
export type CartItem = components["schemas"]["CartItemOut"];
export type CartItemIn = components["schemas"]["CartItemIn"];
export type Cart = components["schemas"]["CartOut"];
export type DrinkOptions = components["schemas"]["DrinkOptionsIn"];
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
export type AdminVariant = components["schemas"]["AdminVariantOut"];
export type AdminCatalogProduct = components["schemas"]["AdminCatalogProductOut"];
export type AdminCatalogPage = components["schemas"]["AdminCatalogPage"];
export type AdminImage = components["schemas"]["AdminImageOut"];
export type AdminImageIn = components["schemas"]["AdminImageIn"];
export type AdminImageUpdateIn = components["schemas"]["AdminImageUpdateIn"];
export type AdminImageOrderIn = components["schemas"]["AdminImageOrderIn"];
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
export type Notice = components["schemas"]["NoticeOut"];
export type AdminNotice = components["schemas"]["AdminNoticeOut"];
export type AdminNoticeIn = components["schemas"]["AdminNoticeIn"];
export type AdminNoticeUpdateIn = components["schemas"]["AdminNoticeUpdateIn"];
export type StorefrontConfig = components["schemas"]["StorefrontConfigOut"];

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

// Like api(), but for multipart form uploads: no Content-Type header (the
// browser sets the multipart boundary itself), body is FormData rather than
// a JSON string. Shares the same credentials/CSRF/error handling as api()
// so callers get the same ApiError/humanizeError behaviour either way.
export async function apiUpload<T>(
  path: string,
  body: FormData,
  options?: Omit<RequestInit, "body">,
): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method: "POST",
    credentials: "include",
    ...options,
    body,
  });
  if (!response.ok) {
    const responseBody = await response.json().catch(() => ({ detail: "Request failed" }));
    const detail = responseBody.detail ?? "Request failed";
    throw new ApiError(response.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

// Turns a thrown error into copy safe to show a user. Business-specific 4xx
// messages (404 "not found", 409 conflicts like sold-out stock) are already
// written in plain English server-side, so those pass through unchanged;
// everything else (auth, rate limits, validation, server errors, or a non-API
// error like a network failure) gets a human fallback instead of a raw status
// code, stack-shaped message, or a JSON.stringify'd validation array.
export const humanizeError = (error: unknown): string => {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Check your email and password and try again.";
    if (error.status === 403) return "You don't have permission to do that.";
    if (error.status === 422) return "That doesn't look right — check the highlighted fields and try again.";
    if (error.status === 429) return "Too many attempts — please wait a moment and try again.";
    if (error.status >= 500) return "Something went wrong on our end — please try again in a moment.";
    return error.message;
  }
  return "Something went wrong. Please try again.";
};

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

// Time-only label for a pickup slot chip, e.g. "16:15". Slot instants are UTC;
// always render café wall-clock time.
export const formatSlotTime = (iso: string) =>
  new Date(iso).toLocaleTimeString([], {
    timeZone: CAFE_TIMEZONE,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

// Friendly "posted" label for a notice: relative for the first day ("just now",
// "3 hours ago"), then a short date so an old notice doesn't read as "9 days
// ago" forever.
export const formatNoticeDate = (iso: string) => {
  const date = new Date(iso);
  const diffMs = Date.now() - date.getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days} day${days === 1 ? "" : "s"} ago`;
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" }).format(date);
};

// The standard recipe every drink option defaults to; only deviations from
// this are worth showing back to the customer on a cart/order line.
const STANDARD_OPTIONS = { matcha_g: 4, whisk: "water", base_milk: "cow", milk_ml: 130, sugar_g: 4 };

// Shared by CartPage and OrderStatusView: summarises only the customisations
// that differ from the standard recipe (e.g. "6 g matcha · oat milk · 6 g
// sugar"), so a default drink shows no clutter at all. Returns null when
// there's nothing to show (non-drink items, or an all-standard drink).
export const formatDrinkOptions = (options: Record<string, unknown> | null | undefined) => {
  if (!options) return null;
  // Keys are only pushed when present and non-standard, so orders placed
  // before a given option existed (missing key -> undefined) render as
  // standard rather than as a spurious "undefined ..." customisation.
  const nonStandard = (key: keyof typeof STANDARD_OPTIONS) =>
    options[key] != null && options[key] !== STANDARD_OPTIONS[key];
  const parts: string[] = [];
  if (nonStandard("matcha_g")) parts.push(`${options.matcha_g} g matcha`);
  if (nonStandard("whisk")) parts.push(`${options.whisk} whisk`);
  if (nonStandard("base_milk")) parts.push(`${options.base_milk} milk`);
  if (nonStandard("milk_ml")) parts.push(`${options.milk_ml} ml milk`);
  if (nonStandard("sugar_g")) parts.push(`${options.sugar_g} g sugar`);
  return parts.length ? parts.join(" · ") : null;
};
