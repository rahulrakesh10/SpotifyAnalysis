#!/bin/bash
# Sets up LibreChat (a chat web app) connected to the ClickHouse tool server.
# Run after: ./setup.sh && docker compose up -d --build
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || ./setup.sh
set -a; . ./.env; set +a

[ -d librechat ] || git clone -q --depth 1 --branch v0.8.8 https://github.com/danny-avila/LibreChat.git librechat
cd librechat

if [ ! -f .env ]; then
  cp .env.example .env
  perl -pi -e "s/^CREDS_KEY=.*/CREDS_KEY=$(openssl rand -hex 32)/" .env
  perl -pi -e "s/^CREDS_IV=.*/CREDS_IV=$(openssl rand -hex 16)/" .env
  perl -pi -e "s/^JWT_SECRET=.*/JWT_SECRET=$(openssl rand -hex 32)/" .env
  perl -pi -e "s/^JWT_REFRESH_SECRET=.*/JWT_REFRESH_SECRET=$(openssl rand -hex 32)/" .env
  perl -pi -e "s/^MEILI_MASTER_KEY=.*/MEILI_MASTER_KEY=$(openssl rand -hex 16)/" .env
  # Each person enters their own Anthropic key in the chat UI, so none is stored here
  perl -pi -e "s/^ANTHROPIC_API_KEY=.*/ANTHROPIC_API_KEY=user_provided/" .env
  printf "\nUID=%s\nGID=%s\nMCP_AUTH_TOKEN=%s\nSCHEDULES_SINGLE_PROCESS=true\nANTHROPIC_MODELS=claude-sonnet-5-5,claude-opus-5-5,claude-haiku-4-5-20251001\n" "$(id -u)" "$(id -g)" "$MCP_AUTH_TOKEN" >> .env
  chmod 600 .env
fi

cp ../librechat-config/librechat.yaml ../librechat-config/docker-compose.override.yml .
docker compose up -d api mongodb meilisearch
echo "LibreChat: http://localhost:3080  (create an account, then add your Anthropic API key when asked)"
