# ADR 0008: Pickup scheduling and the adaptive checkout

Status: accepted

Drinks are made to order and picked up at the dorm kitchen; retail items may ship.
Checkout therefore adapts to the cart instead of always demanding a shipping address:
the cart declares `needs_pickup` (contains any drink) and `needs_shipping` (contains any
non-drink), and the API validates that a pickup order carries a valid slot and a shipped
order carries an address. Mixed carts need both.

Decisions and reasons:

- **Admin-defined pickup days, derived slots.** A `pickup_days` row holds a date, a
  serving window, a slot interval and a per-slot capacity; concrete time slots are
  derived, never stored. This is ported from the legacy café schema — storing slots as
  rows would require generating and maintaining them; deriving them makes capacity and
  window changes retroactively consistent.
- **Capacity is checked under a row lock.** The checkout transaction locks the
  `pickup_days` row (`SELECT … FOR UPDATE`) before counting bookings in the requested
  slot. The legacy app validated capacity *outside* the write lock and double-booked
  slots under concurrency — the check must happen under the same lock that serializes
  the writes it is guarding (the same rule ADR-recorded for stock reservations).
- **Cancelled and expired orders free their slot** by being excluded from the count, so
  no explicit "release" bookkeeping exists to get wrong.
- **Shipping countries: an empty allowlist means allow-all.** Retail isn't actively sold
  yet, so the gate is open; when it matters, populating the list re-enables restriction
  without a code change.
- **The receipt follows the fulfillment.** Order confirmation emails show the pickup
  time for pickup orders and the address block only when one exists — the email renders
  what the order is, not what the form once looked like.
