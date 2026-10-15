"""Run SQL through the MCP tool server, exactly as the agent would. Needs the stack running.

    python3 query.py "SELECT count() FROM spotify.songs"
"""
import json
import sys
import urllib.request
from pathlib import Path

URL = "http://127.0.0.1:8000/mcp"          # free-form SQL tool server
SONGS_URL = "http://127.0.0.1:8001/mcp"    # ready-made song tools
TOKEN = next(l.split("=", 1)[1].strip() for l in (Path(__file__).parent / ".env").read_text().splitlines()
             if l.startswith("MCP_AUTH_TOKEN="))
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
           "Accept": "application/json, text/event-stream"}


def post(body, session=None, url=None):
    headers = dict(HEADERS, **({"Mcp-Session-Id": session} if session else {}))
    resp = urllib.request.urlopen(urllib.request.Request(url or URL, json.dumps(body).encode(), headers))
    return resp.headers.get("mcp-session-id"), resp.read().decode()


def _session(url):
    session, _ = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "query.py", "version": "0"}}}, url=url)
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session, url)
    return session


def _result(text):
    data = next(l[6:] for l in text.splitlines() if l.startswith("data: "))
    return json.loads(data)["result"]


def list_tools(url=SONGS_URL):
    """The tools a server offers, as [{name, description, inputSchema}]."""
    session = _session(url)
    _, text = post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, session, url)
    return _result(text)["tools"]


def call_tool(name, arguments, url=SONGS_URL):
    """Call one tool. Returns (ok, parsed_result_or_error_text)."""
    session = _session(url)
    _, text = post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": name, "arguments": arguments}}, session, url)
    result = _result(text)
    body = result["content"][0]["text"]
    if result.get("isError"):
        return False, body
    try:
        return True, json.loads(body)
    except ValueError:
        return True, body


def run(queries):
    """Run each SQL string through the tool server. Returns a list of (ok, parsed_or_error_text)."""
    session, _ = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "query.py", "version": "0"}}})
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
    results = []
    for sql in queries:
        _, text = post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                        "params": {"name": "run_query", "arguments": {"query": sql}}}, session)
        data = next(l[6:] for l in text.splitlines() if l.startswith("data: "))
        result = json.loads(data)["result"]
        body = result["content"][0]["text"]
        results.append((False, body) if result.get("isError") else (True, json.loads(body)))
    return results


def main(queries):
    for ok, body in run(queries):
        print(json.dumps(body, ensure_ascii=False)[:800] if ok else "ERROR: " + body[:800])


if __name__ == "__main__":
    main(sys.argv[1:])
