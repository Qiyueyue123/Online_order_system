# ADR 0001: Opaque server-side sessions

Status: accepted

Use random session tokens in secure HTTP-only, SameSite cookies. Store only their SHA-256
hashes, expiry, revocation and CSRF token in PostgreSQL.

This permits immediate revocation and prevents browser JavaScript from reading credentials.
JWTs were rejected because this application benefits more from straightforward revocation than
from stateless verification.
