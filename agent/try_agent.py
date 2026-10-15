"""Try the Song Analyst with a local Ollama model, using the same instructions and database tool
that LibreChat uses. Needs the stack running (./start.sh) and Ollama running.

    python3 try_agent.py "Which genres grow fastest among 2025 releases?" [--model song-analyst]
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

import yaml

from query import run

OLLAMA = "http://127.0.0.1:11434/api/chat"
SPEC = yaml.safe_load((Path(__file__).parent / "librechat-config" / "librechat.yaml").read_text())["modelSpecs"]["list"][0]
INSTRUCTIONS = SPEC["preset"]["instructions"]
TOOLS = [{"type": "function", "function": {
    "name": "run_query",
    "description": "Run a read-only SQL SELECT against the ClickHouse database and return the rows.",
    "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "ClickHouse SQL"}},
                   "required": ["query"]}}}]


def chat(model, messages):
    body = {"model": model, "messages": messages, "tools": TOOLS, "stream": False,
            "options": {"num_ctx": 8192, "temperature": 0.1}, "keep_alive": "30s"}
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=600).read())["message"]


def ask(question, model, max_steps=6, quiet=False):
    """Returns (answer, sqls_run). Prints each tool call unless quiet."""
    sqls = []
    messages = [{"role": "system", "content": INSTRUCTIONS}, {"role": "user", "content": question}]
    for _ in range(max_steps):
        msg = chat(model, messages)
        messages.append(msg)
        if not msg.get("tool_calls"):
            return msg.get("content", ""), sqls
        for call in msg["tool_calls"]:
            sql = call["function"]["arguments"].get("query", "")
            sqls.append(sql)
            if not quiet:
                print(f"  [tool] {sql[:300]}")
            ok, body = run([sql])[0]
            text = json.dumps(body, ensure_ascii=False)[:3000] if ok else "ERROR: " + body[:500]
            if not quiet:
                print(f"  [result] {text[:200]}")
            messages.append({"role": "tool", "content": text})
    return "(stopped: too many tool calls)", sqls


if __name__ == "__main__":
    args = sys.argv[1:]
    model = "song-analyst"
    if "--model" in args:
        i = args.index("--model"); model = args[i + 1]; del args[i:i + 2]
    try:
        for q in args:
            print(f"\nQ: {q}")
            start = time.time()
            print("\n" + ask(q, model)[0] + f"\n\n({time.time() - start:.0f}s)")
    finally:  # free the model's memory straight away
        urllib.request.urlopen(urllib.request.Request(
            "http://127.0.0.1:11434/api/generate", json.dumps({"model": model, "keep_alive": 0}).encode(),
            {"Content-Type": "application/json"}))
