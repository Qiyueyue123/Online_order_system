# Matcha_Online_sys

Small home cafe ordering system for very low traffic. This repository is now set up as a beginner-friendly Python web app project that can be run locally with a `venv` and deployed in a container with Docker.

## Why this stack

This starter uses:
- `Flask` for a small server-rendered web app
- `SQLite` for a simple local database
- `Gunicorn` as the production app server
- `Docker` for packaging the app into a deployable container

This is a good learning stack because it shows the full path from:
1. local development
2. dependency management with a virtual environment
3. persistent data
4. production serving
5. containerized deployment

## Current product direction

Current assumptions:
- Max around 50 users
- Main use case is online ordering with pickup time slots
- Focus on simple operations, not a full restaurant platform
- Version 1 uses `cash on pickup`
- Optional manual `Tikkie on pickup` can exist as a low-automation fallback
- No full payment gateway in version 1
- Use a relational database design for orders, products, and pickup data
- Inventory is tracked by shared matcha stock pools

## Project structure

```text
.
├── app/
│   ├── __init__.py
│   ├── db.py
│   ├── routes.py
│   ├── schema.sql
│   ├── static/
│   └── templates/
├── tests/
├── Dockerfile
├── docker-compose.yml
├── docker-entrypoint.sh
├── requirements.txt
├── requirements-dev.txt
└── run.py
```

## What the app already does

The starter app includes:
- menu page
- admin-managed homepage alert banner
- multi-image galleries visible directly on the home page
- dedicated drink detail pages
- multi-image drink galleries
- admin-uploadable drink images
- admin image reordering controls
- admin image deletion controls
- admin stock editing
- admin product create/update/delete
- checkout form
- two preparation style options for each drink
- selectable pickup datetime slots
- phone entry limited to the last 4 digits
- payment method selection
- order confirmation page
- real admin user login with session-based authentication
- health check endpoint at `/healthz`
- SQLite database initialization command
- SQLite database reset command
- Docker startup flow
- basic tests
- optional product image support in the schema
- a `product_images` table for multi-image drink pages

## How to start locally with `venv`

### 1. Create the virtual environment

```bash
python3 -m venv .venv
```

This creates an isolated Python environment inside the project folder.

### 2. Activate it

On macOS or Linux:

```bash
source .venv/bin/activate
```

When it is active, your terminal prompt usually shows `(.venv)`.

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

Why `requirements-dev.txt`:
- it installs the app dependencies
- it also installs `pytest` so you can run tests

### 4. Reset the database once after schema changes

If you already ran an older version of the project, reset the local database first:

```bash
python -m flask --app run reset-db
```

This recreates the SQLite file with the current schema and seed data.

Run this again whenever you change database fields such as orders, alerts, or product tables.

### 5. Initialize the database

For a fresh setup:

```bash
python -m flask --app run init-db
```

This creates the SQLite schema and seeds sample menu items.

### 6. Run the app in development

```bash
FLASK_DEBUG=1 python run.py
```

Then open:

```text
http://127.0.0.1:8000
```

Useful routes:
- `/` for the menu
- `/checkout` for the order form
- `/admin/login` for the admin login page
- `/admin` for the admin dashboard after login
- `/healthz` for the deployment health check

### 7. Run tests

```bash
pytest
```

### Admin login for local development

Defaults:
- username: `admin`
- password: `change-me-admin`

Where to change admin credentials:
- your local shell environment before running `python run.py`
- your local `.env` file for Docker Compose
- your production host's secret or environment-variable settings

For anything beyond local testing, set your own values with environment variables:

```bash
export ADMIN_USERNAME=your-admin-name
export ADMIN_PASSWORD=your-strong-password
```

How it works now:
- the app stores admin accounts in the `admin_users` table
- on startup, the app creates or updates the bootstrap admin user from your environment variables
- login checks the database record, not just in-memory config values

If you prefer to provide a precomputed password hash instead of a raw password:

```bash
python -m flask --app run hash-password "your-strong-password"
export ADMIN_USERNAME=your-admin-name
export ADMIN_PASSWORD_HASH='paste-a-werkzeug-password-hash-here'
```

Recommended secure setup:
- set a strong `SECRET_KEY`
- use `ADMIN_PASSWORD_HASH` for deployment so you are not storing a raw password in app config
- keep real secrets out of Git-tracked files
- use the default `admin / change-me-admin` only for local development

For Docker Compose, copy the template and fill in your own values:

```bash
cp .env.example .env
python -m flask --app run hash-password "your-strong-password"
```

Then paste the generated hash into `.env` as `ADMIN_PASSWORD_HASH`.

Admin-uploaded images are stored in the instance upload folder and served by the app:
- local folder: `instance/uploads/`
- public URL pattern: `/uploads/<filename>`

## How Docker fits in

`venv` and Docker solve different problems:

- `venv` isolates Python packages on your own machine during development
- `Docker` packages the whole app into a consistent runtime that can be deployed elsewhere

You still learn both because a real deployable project usually has:
- a local developer workflow
- a deployment workflow

## How to run with Docker

### Option A: use Docker Compose

```bash
docker compose up --build
```

Then open:

```text
http://127.0.0.1:8000
```

### Option B: build and run manually

Build the image:

```bash
docker build -t matcha-home-cafe .
```

Run the container:

```bash
docker run --rm -p 8000:8000 \
  -e SECRET_KEY=change-me \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD=change-me-admin \
  -e DATABASE_PATH=/app/instance/matcha.db \
  -v "$(pwd)/instance:/app/instance" \
  matcha-home-cafe
```

Why the volume matters:
- the SQLite database file lives in `/app/instance`
- without a mounted volume, container data disappears when the container stops

Docker Compose now reads secrets from your local `.env` file or shell environment instead of hardcoding them in [docker-compose.yml](/Users/qy/Documents/GitHub/Matcha_Online_sys/docker-compose.yml).

## How this becomes a deployable website

This project is now close to a basic deployment shape:
- app code is separated from startup config
- production serving uses `gunicorn`
- the app exposes one port
- there is a health endpoint
- Docker can package the app for deployment

What you would improve next for a stronger showcase:
- replace free-text pickup slot input with selectable time slots
- add create/update views for products and images
- add a proper migration workflow
- move from SQLite to PostgreSQL when traffic or features grow
- deploy to a platform such as Render, Railway, Fly.io, or a VPS

## Suggested learning path

Follow this order:
1. Run the project with `venv`
2. Read `run.py`, [app/__init__.py](/Users/qy/Documents/GitHub/Matcha_Online_sys/app/__init__.py), [app/routes.py](/Users/qy/Documents/GitHub/Matcha_Online_sys/app/routes.py), and [app/db.py](/Users/qy/Documents/GitHub/Matcha_Online_sys/app/db.py)
3. Place a few test orders through the browser
4. Inspect the SQLite database file in `instance/`
5. Run `pytest`
6. Run the app with Docker
7. Change one feature and rebuild the container

## Progress log

### 2026-04-07

- Defined product direction: home cafe pickup ordering system
- Confirmed this is a very small-scale project, so simplicity matters more than payment automation
- Decided the safest MVP payment flow is pay on pickup
- Noted that Netherlands-local payment expectations are relevant, but full payment integration is optional for this project size
- Identified `cash on pickup` as the best starting option

### 2026-04-09

- Chose Python + Flask as the teaching stack
- Added a real starter app structure instead of keeping the repo empty
- Added SQLite-backed order storage
- Added templates and styling for a minimal web UI
- Added Docker support for a deployable container workflow
- Added tests so the project demonstrates basic verification
- Updated the README to explain `venv`, local setup, and Docker usage
- Verified local `venv` setup, dependency installation, database initialization, and test execution
- Confirmed `docker compose config` is valid
- Full Docker image build was not verified in this session because the local Docker daemon was not running
- Decided that SQL is the better learning and showcase choice than MongoDB for this project type
- Added shared inventory tracking for Ikuyo and Sayaka stock
- Replaced query-string admin access with a real login flow
- Removed most filler text from the UI and tightened the storefront presentation
- Added optional product image fields for future menu photos
- Added a proper multi-image drink gallery with a dedicated drink detail page
- Added admin image uploads stored in the writable instance folder
- Moved admin authentication to a real `admin_users` database table bootstrapped from environment variables
- Made drink image galleries viewable from the home page without leaving the menu
- Added admin controls to reorder drink gallery images
- Added admin CRUD tools for products, stock levels, and image deletion
- Added visible overlay arrow controls to the home-page drink galleries
- Added a CLI password-hash command so admin auth can use hashed environment values
- Switched Docker Compose away from hardcoded admin secrets and added a `.env.example` template
- Upgraded the drink galleries to animate with a sliding transition instead of instant image swaps
- Added admin-controlled homepage alerts that display on the menu page
- Replaced free-text pickup entry with selectable datetime slots
- Simplified customer identification to the last 4 phone digits

## Notes

This README should be updated periodically as project decisions change and implementation progresses.
