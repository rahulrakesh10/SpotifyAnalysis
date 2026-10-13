#!/bin/bash
# Creates agent/.env with random passwords the first time. Nothing secret is committed.
cd "$(dirname "$0")"
if [ -f .env ]; then echo ".env already exists, leaving it alone"; exit 0; fi
cat > .env <<ENV
CLICKHOUSE_ADMIN_PASSWORD=$(openssl rand -hex 16)
AGENT_RO_PASSWORD=$(openssl rand -hex 16)
MCP_AUTH_TOKEN=$(openssl rand -hex 24)
ENV
chmod 600 .env
echo "Created agent/.env"
