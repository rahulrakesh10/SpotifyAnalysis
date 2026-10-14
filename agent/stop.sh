#!/bin/bash
# Stops everything and frees memory. Your data is kept and comes back with ./start.sh.
cd "$(dirname "$0")"
(cd librechat && docker compose down)
docker compose down
# Unload any local models right away (they otherwise stay in memory for minutes)
for m in $(ollama ps 2>/dev/null | awk 'NR>1{print $1}'); do ollama stop "$m"; done
# Quit Docker Desktop too, unless another project still has containers running
if [ -z "$(docker ps -q)" ]; then
  osascript -e 'quit app "Docker"'; echo "Docker Desktop quit to free memory"
else
  echo "Docker left running: other containers are still up ($(docker ps --format '{{.Names}}' | paste -sd, -))"
fi
