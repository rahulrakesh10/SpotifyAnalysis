#!/bin/bash
# Stops and removes the containers. Your data is kept and comes back with ./start.sh.
cd "$(dirname "$0")"
(cd librechat && docker compose down)
docker compose down
