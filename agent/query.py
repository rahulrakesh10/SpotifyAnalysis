"""Run SQL through the MCP tool server, exactly as the agent would. Needs the stack running.

    python3 query.py "SELECT count() FROM spotify.songs"
"""
import json
import sys
import urllib.request
from pathlib import Path

URL = "http://127.0.0.1:8000/mcp"
TOKEN = next(l.split("=", 1)[1].strip() for l in (Path(__file__).parent / ".env").read_text().splitlines()
             if l.startswith("MCP_AUTH_TOKEN="))
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
           "Accept": "application/json, text/event-stream"}


def post(body, session=None):
    headers = dict(HEADERS, **({"Mcp-Session-Id": session} if session else {}))
    resp = urllib.request.urlopen(urllib.request.Request(URL, json.dumps(body).encode(), headers))
    return resp.headers.get("mcp-session-id"), resp.read().decode()


def main(queries):
    session, _ = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "query.py", "version": "0"}}})
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
    for sql in queries:
        _, text = post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                        "params": {"name": "run_query", "arguments": {"query": sql}}}, session)
        data = next(l[6:] for l in text.splitlines() if l.startswith("data: "))
        result = json.loads(data)["result"]
        print(("ERROR: " if result.get("isError") else "") + result["content"][0]["text"][:800])


if __name__ == "__main__":
    main(sys.argv[1:])
