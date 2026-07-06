# Catalog-to-order walkthrough

1. `CatalogPage` loads `/api/v1/products`; the catalog service applies active, search, category
   and pagination filters.
2. Adding a variant calls `PUT /api/v1/cart/items`. Anonymous carts receive an HTTP-only token;
   the database stores only its hash.
3. `CheckoutPage` sends identity and address, never price. The checkout service locks variants,
   reads current SGD prices, validates the country and coupon, and creates item snapshots.
4. The same commit creates inventory movements and a pending payment. The API then creates a
   Stripe test Checkout Session when test credentials are configured.
5. A signed webhook consumes stock and changes payment/order states. Order reads require either
   the owning account, an administrator, or the guest secret.

## Debugging map

- Browser: Network tab for `/api/v1` status and cookie presence; accessibility tree for labels.
- API: request logs and OpenAPI at `/docs`; never print session or guest tokens.
- Database: inspect `orders`, `payments`, `inventory_movements`, and `processed_webhooks`.
- Stripe: use test event delivery logs and resend the same event to confirm idempotency.
- AWS: start at ALB target health, then ECS logs, RDS connectivity and CloudFront origin errors.

## Exercises

1. Add a new flat-rate zone and a test proving unsupported countries still fail.
2. Add a quantity decrement control that keeps the API authoritative.
3. Add a `shipped` transition and reject it unless the order is paid.
