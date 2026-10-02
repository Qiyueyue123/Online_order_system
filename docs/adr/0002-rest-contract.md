# ADR 0002: Versioned REST and generated types

Status: accepted

Expose `/api/v1` JSON resources and publish FastAPI's OpenAPI document. Generate TypeScript
declarations with `openapi-typescript`. CI builds both sides; incompatible schema edits become
visible before deployment.
