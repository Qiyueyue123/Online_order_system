#!/bin/sh
set -e

python -m flask --app run init-db
exec "$@"
