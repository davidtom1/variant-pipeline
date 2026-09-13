#!/bin/sh
# Run the full pipeline as the current user, so output files are owned by you
# rather than by root. See README for details.
UID_=$(id -u)
GID_=$(id -g)
export UID=$UID_ GID=$GID_
exec docker compose up --build "$@"
