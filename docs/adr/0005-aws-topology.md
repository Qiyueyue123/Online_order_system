# ADR 0005: Cost-controlled AWS topology

Status: accepted

Use private S3 plus CloudFront for React, ECS Fargate behind an ALB for FastAPI, single-AZ RDS
PostgreSQL, S3 media, SES, ECR, Secrets Manager and CloudWatch. Route 53 and ACM keep the frontend
and API under one parent domain. Single-AZ RDS is a deliberate showcase cost tradeoff, not a
high-availability production recommendation.
