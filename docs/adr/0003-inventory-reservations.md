# ADR 0003: Transactional inventory reservations

Status: accepted

At checkout, lock every requested variant, calculate availability and increment reserved stock
in one database transaction. Successful webhook processing decrements both reserved and on-hand
stock. Expiry decrements reserved stock only. Every mutation receives an audit movement.

The database constraints make negative or over-reserved inventory invalid even if application
logic regresses.
