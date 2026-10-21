#!/bin/bash
# Starts everything: ClickHouse, the tool server and LibreChat. Data is kept between runs.
cd "$(dirname "$0")"
# The local model LibreChat uses (made from llama3.2; no download). Needs Ollama installed.
if command -v ollama >/dev/null; then
  ollama list | grep -q "^song-analyst:" || ollama create song-analyst -f ollama/Modelfile
  # the 8B model is the default; it needs `ollama pull llama3.1:8b` once (about 5 GB)
  if ollama list | grep -q "^llama3.1:8b" && ! ollama list | grep -q "^song-analyst-8b"; then
    ollama create song-analyst-8b -f ollama/Modelfile.8b
  fi
fi
open -a Docker 2>/dev/null
until docker info >/dev/null 2>&1; do sleep 2; done
docker compose up -d
cp librechat-config/librechat.yaml librechat-config/docker-compose.override.yml librechat/   # pick up any edits
(cd librechat && docker compose up -d api mongodb meilisearch)
echo "Ready: http://localhost:3080"
